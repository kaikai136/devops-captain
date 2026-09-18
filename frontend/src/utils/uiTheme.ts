import type { UiThemeConfig, UiThemePreset } from '../types';

export const uiThemePresetColors: Record<Exclude<UiThemePreset, 'custom'>, string> = {
  neutral: '#18181B',
  slate: '#334155',
  blue: '#2563EB',
  cyan: '#0891B2',
  teal: '#0F766E',
  emerald: '#059669',
};

export const uiThemePresetOptions: Array<{ value: UiThemePreset; label: string; color: string }> = [
  { value: 'neutral', label: 'Neutral', color: uiThemePresetColors.neutral },
  { value: 'slate', label: 'Slate', color: uiThemePresetColors.slate },
  { value: 'blue', label: 'Blue', color: uiThemePresetColors.blue },
  { value: 'cyan', label: 'Cyan', color: uiThemePresetColors.cyan },
  { value: 'teal', label: 'Teal', color: uiThemePresetColors.teal },
  { value: 'emerald', label: 'Emerald', color: uiThemePresetColors.emerald },
  { value: 'custom', label: 'Custom', color: '#71717A' },
];

export const defaultUiTheme: UiThemeConfig = {
  preset: 'blue',
  customPrimary: '#2563EB',
};

const presetNames = new Set<UiThemePreset>(uiThemePresetOptions.map((option) => option.value));

interface RgbColor {
  red: number;
  green: number;
  blue: number;
}

interface HslColor {
  hue: number;
  saturation: number;
  lightness: number;
}

export interface UiThemePalette {
  primary: string;
  lightPrimary: string;
  darkPrimary: string;
  lightPrimaryForeground: string;
  darkPrimaryForeground: string;
  lightCharts: string[];
  darkCharts: string[];
}

export function normalizeHexColor(value: unknown, fallback = defaultUiTheme.customPrimary) {
  const color = String(value ?? '').trim();
  return /^#[0-9a-fA-F]{6}$/.test(color) ? color.toUpperCase() : fallback;
}

export function normalizeUiThemeConfig(value: unknown): UiThemeConfig {
  const raw = value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  const presetValue = String(raw.preset ?? '').trim().toLowerCase() as UiThemePreset;
  return {
    preset: presetNames.has(presetValue) ? presetValue : defaultUiTheme.preset,
    customPrimary: normalizeHexColor(raw.customPrimary),
  };
}

export function resolveUiThemePrimary(config: UiThemeConfig) {
  const normalized = normalizeUiThemeConfig(config);
  return normalized.preset === 'custom' ? normalized.customPrimary : uiThemePresetColors[normalized.preset];
}

export function getContrastForeground(background: string) {
  const rgb = hexToRgb(normalizeHexColor(background));
  const luminance = [rgb.red, rgb.green, rgb.blue]
    .map((channel) => channel / 255)
    .map((channel) => (channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4))
    .reduce((total, channel, index) => total + channel * [0.2126, 0.7152, 0.0722][index], 0);
  return luminance > 0.46 ? '#09090B' : '#FFFFFF';
}

export function buildUiThemePalette(config: UiThemeConfig): UiThemePalette {
  const primary = resolveUiThemePrimary(config);
  const hsl = rgbToHsl(hexToRgb(primary));
  const lightPrimary = primary;
  const darkPrimary = hslToHex({
    hue: hsl.hue,
    saturation: Math.max(48, hsl.saturation),
    lightness: Math.max(62, Math.min(72, hsl.lightness + 24)),
  });
  const chartOffsets = [0, 46, 92, 166, 222];
  const lightCharts = chartOffsets.map((offset, index) =>
    hslToHex({
      hue: (hsl.hue + offset) % 360,
      saturation: Math.max(48, Math.min(82, hsl.saturation + (index % 2 === 0 ? 0 : -8))),
      lightness: Math.max(38, Math.min(60, hsl.lightness + (index === 0 ? 0 : 5))),
    }),
  );
  const darkCharts = chartOffsets.map((offset, index) =>
    hslToHex({
      hue: (hsl.hue + offset) % 360,
      saturation: Math.max(52, Math.min(86, hsl.saturation + (index % 2 === 0 ? 4 : -4))),
      lightness: 64 + (index % 2) * 4,
    }),
  );
  return {
    primary,
    lightPrimary,
    darkPrimary,
    lightPrimaryForeground: getContrastForeground(lightPrimary),
    darkPrimaryForeground: getContrastForeground(darkPrimary),
    lightCharts,
    darkCharts,
  };
}

export function applyUiTheme(root: HTMLElement, config: UiThemeConfig) {
  const palette = buildUiThemePalette(config);
  const lightRgb = hexToRgb(palette.lightPrimary);
  const darkRgb = hexToRgb(palette.darkPrimary);
  root.style.setProperty('--ui-primary-light', palette.lightPrimary);
  root.style.setProperty('--ui-primary-dark', palette.darkPrimary);
  root.style.setProperty('--ui-primary-light-rgb', rgbString(lightRgb));
  root.style.setProperty('--ui-primary-dark-rgb', rgbString(darkRgb));
  root.style.setProperty('--ui-primary-foreground-light', palette.lightPrimaryForeground);
  root.style.setProperty('--ui-primary-foreground-dark', palette.darkPrimaryForeground);
  palette.lightCharts.forEach((color, index) => root.style.setProperty(`--ui-chart-${index + 1}-light`, color));
  palette.darkCharts.forEach((color, index) => root.style.setProperty(`--ui-chart-${index + 1}-dark`, color));
}

function hexToRgb(hex: string): RgbColor {
  const value = Number.parseInt(hex.slice(1), 16);
  return {
    red: (value >> 16) & 255,
    green: (value >> 8) & 255,
    blue: value & 255,
  };
}

function rgbString(color: RgbColor) {
  return `${color.red}, ${color.green}, ${color.blue}`;
}

function rgbToHsl(color: RgbColor): HslColor {
  const red = color.red / 255;
  const green = color.green / 255;
  const blue = color.blue / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const delta = max - min;
  let hue = 0;
  if (delta) {
    if (max === red) hue = 60 * (((green - blue) / delta) % 6);
    else if (max === green) hue = 60 * ((blue - red) / delta + 2);
    else hue = 60 * ((red - green) / delta + 4);
  }
  const lightness = (max + min) / 2;
  const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1));
  return {
    hue: (hue + 360) % 360,
    saturation: saturation * 100,
    lightness: lightness * 100,
  };
}

function hslToHex(color: HslColor) {
  const saturation = color.saturation / 100;
  const lightness = color.lightness / 100;
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const section = color.hue / 60;
  const secondary = chroma * (1 - Math.abs((section % 2) - 1));
  const channels =
    section < 1 ? [chroma, secondary, 0] :
      section < 2 ? [secondary, chroma, 0] :
        section < 3 ? [0, chroma, secondary] :
          section < 4 ? [0, secondary, chroma] :
            section < 5 ? [secondary, 0, chroma] : [chroma, 0, secondary];
  const match = lightness - chroma / 2;
  return `#${channels.map((channel) => Math.round((channel + match) * 255).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}
