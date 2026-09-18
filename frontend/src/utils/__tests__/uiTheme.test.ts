import { describe, expect, it } from 'vitest';

import {
  buildUiThemePalette,
  defaultUiTheme,
  getContrastForeground,
  normalizeUiThemeConfig,
  resolveUiThemePrimary,
} from '../uiTheme';

describe('ui theme', () => {
  it('normalizes presets and custom colors', () => {
    expect(normalizeUiThemeConfig(null)).toEqual(defaultUiTheme);
    expect(normalizeUiThemeConfig({ preset: 'TEAL', customPrimary: '#abcdef' })).toEqual({
      preset: 'teal',
      customPrimary: '#ABCDEF',
    });
    expect(normalizeUiThemeConfig({ preset: 'unknown', customPrimary: 'red' })).toEqual(defaultUiTheme);
  });

  it('uses the custom primary only for custom themes', () => {
    expect(resolveUiThemePrimary({ preset: 'blue', customPrimary: '#FF0000' })).toBe('#2563EB');
    expect(resolveUiThemePrimary({ preset: 'custom', customPrimary: '#A855F7' })).toBe('#A855F7');
  });

  it('generates readable light and dark palettes with five chart colors', () => {
    const palette = buildUiThemePalette({ preset: 'custom', customPrimary: '#F8FAFC' });
    expect(palette.lightPrimaryForeground).toBe('#09090B');
    expect(palette.darkPrimaryForeground).toMatch(/^#(?:09090B|FFFFFF)$/);
    expect(palette.lightCharts).toHaveLength(5);
    expect(palette.darkCharts).toHaveLength(5);
    expect(new Set(palette.lightCharts).size).toBe(5);
    expect(getContrastForeground('#111827')).toBe('#FFFFFF');
  });
});
