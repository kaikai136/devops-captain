import { ref } from 'vue';

import { createSystemSetting, getSystemSettingOrNull, updateSystemSetting, type SystemSettingPayload } from '../../services/system';
import type {
  AccountUser,
  DashboardHeroConfig,
  LayoutFooterConfig,
  LoginContentConfig,
  SiteIdentityConfig,
  SystemSetting,
  TemplateVariables,
  UiThemeConfig,
} from '../../types';
import { defaultUiTheme, normalizeUiThemeConfig } from '../../utils/uiTheme';

export const SITE_IDENTITY_SETTING_KEY = 'site_identity';
export const DASHBOARD_HERO_SETTING_KEY = 'dashboard_hero';
export const LAYOUT_FOOTER_SETTING_KEY = 'layout_footer';
export const LOGIN_CONTENT_SETTING_KEY = 'login_content';
export const UI_THEME_SETTING_KEY = 'ui_theme';
export const README_TYPING_SVG_URL = 'https://readme-typing-svg.demolab.com';

export const dashboardHeroFontOptions = ['Noto Sans SC', 'Noto Serif SC', 'Noto Sans TC', 'Noto Serif TC'];
export const dashboardHeroLetterSpacingOptions = [
  { value: 'normal', label: '常规 normal' },
  { value: '0.02em', label: '微宽 0.02em' },
  { value: '0.04em', label: '宽松 0.04em' },
  { value: '0.08em', label: '加宽 0.08em' },
  { value: '1px', label: '轻微 1px' },
  { value: '2px', label: '明显 2px' },
];

export const defaultSiteIdentity: SiteIdentityConfig = {
  appName: '运维船长',
  appShortName: 'CAPTAIN',
  appSubtitle: 'Secure Console',
  browserTitle: '运维船长',
  logoText: 'CAPTAIN',
  logoImageUrl: '/captain-banner.png',
  iconUrl: '/ops-captain-icon.png',
  totpIssuer: '运维船长',
};

export const defaultDashboardHero: DashboardHeroConfig = {
  badgeTemplate: '{appShortName} OPS',
  line1Template: '{greeting}，{displayName}',
  line2Template: '一路向前，莫问前程！！！',
  descriptionTemplate: '这里汇总系统账号、资产与网络出口状态，帮助你快速判断今天的运维态势。',
  font: 'Noto Sans SC',
  fontSize: 24,
  fontWeight: 900,
  letterSpacing: 'normal',
  durationMs: 5000,
  pauseMs: 1000,
  color: '#9B5CFF',
  backgroundColor: '#00000000',
  centered: false,
  verticalCentered: true,
  multiline: false,
  repeat: true,
  random: false,
  width: 620,
  height: 64,
};

export const defaultLayoutFooter: LayoutFooterConfig = {
  enabled: true,
  textTemplate: '© Copyright {year} {appName} All rights reserved.',
  linkText: '',
  linkUrl: '',
  fontSize: 12,
  color: '#0B5CFF',
};

export const defaultLoginContent: LoginContentConfig = {
  badgeTemplate: '{appName} · {appSubtitle}',
  title: '欢迎回来',
  description: '登录管理平台，继续处理网络、主机和系统管理任务。',
  copyrightTemplate: '© {year} {appName} Team',
};

const fontChoices = new Set<string>(dashboardHeroFontOptions);
const fontWeightChoices = new Set([400, 500, 600, 700, 800, 900]);
const letterSpacingChoices = new Set<string>(dashboardHeroLetterSpacingOptions.map((option) => option.value));

interface SiteSettingsFeedback {
  showToast?: (title: string, message?: string, tone?: 'success' | 'error' | 'info') => void;
}

interface TemplateVariableInput {
  siteIdentity: SiteIdentityConfig;
  user?: AccountUser | null;
  localIp?: string | null;
  generatedAt?: string | null;
  now?: Date;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function cleanText(value: unknown, fallback: string, maxLength = 160) {
  const text = String(value ?? '').trim();
  return (text || fallback).slice(0, maxLength);
}

function cleanOptionalText(value: unknown, maxLength = 160) {
  return String(value ?? '').trim().slice(0, maxLength);
}

function isSafeUrl(value: string) {
  if (!value) return true;
  if (value.startsWith('/') && !value.startsWith('//')) return true;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

function cleanUrl(value: unknown, fallback: string, allowBlank = false) {
  const url = String(value ?? '').trim();
  if (!url) return allowBlank ? '' : fallback;
  return isSafeUrl(url) ? url : fallback;
}

function cleanColor(value: unknown, fallback: string) {
  const color = String(value ?? '').trim();
  return /^#[0-9a-fA-F]{6}$/.test(color) ? color.toUpperCase() : fallback;
}

function cleanFont(value: unknown, fallback: string) {
  const font = cleanText(value, fallback, 80);
  return fontChoices.has(font) ? font : fallback;
}

function cleanSvgColor(value: unknown, fallback: string, allowAlpha = false) {
  const color = String(value ?? '').trim();
  const pattern = allowAlpha ? /^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/ : /^#[0-9a-fA-F]{6}$/;
  return pattern.test(color) ? color.toUpperCase() : fallback;
}

function cleanLetterSpacing(value: unknown, fallback: string) {
  const spacing = String(value ?? '').trim() || fallback;
  return letterSpacingChoices.has(spacing) ? spacing : fallback;
}

function cleanInt(value: unknown, fallback: number, min: number, max: number) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, Math.round(number)));
}

function cleanFontWeight(value: unknown, fallback: number) {
  const weight = cleanInt(value, fallback, 400, 900);
  return fontWeightChoices.has(weight) ? weight : fallback;
}

export function normalizeSiteIdentity(value: unknown): SiteIdentityConfig {
  const raw = isRecord(value) ? value : {};
  return {
    appName: cleanText(raw.appName, defaultSiteIdentity.appName, 80),
    appShortName: cleanText(raw.appShortName, defaultSiteIdentity.appShortName, 32),
    appSubtitle: cleanText(raw.appSubtitle, defaultSiteIdentity.appSubtitle, 80),
    browserTitle: cleanText(raw.browserTitle, defaultSiteIdentity.browserTitle, 80),
    logoText: cleanText(raw.logoText, defaultSiteIdentity.logoText, 32),
    logoImageUrl: cleanUrl(raw.logoImageUrl, defaultSiteIdentity.logoImageUrl),
    iconUrl: cleanUrl(raw.iconUrl, defaultSiteIdentity.iconUrl),
    totpIssuer: cleanText(raw.totpIssuer, defaultSiteIdentity.totpIssuer, 80),
  };
}

export function normalizeDashboardHero(value: unknown): DashboardHeroConfig {
  const raw = isRecord(value) ? value : {};
  return {
    badgeTemplate: cleanText(raw.badgeTemplate, defaultDashboardHero.badgeTemplate, 160),
    line1Template: cleanText(raw.line1Template, defaultDashboardHero.line1Template, 160),
    line2Template: cleanText(raw.line2Template, defaultDashboardHero.line2Template, 160),
    descriptionTemplate: cleanText(raw.descriptionTemplate, defaultDashboardHero.descriptionTemplate, 260),
    font: cleanFont(raw.font, defaultDashboardHero.font),
    fontSize: cleanInt(raw.fontSize, defaultDashboardHero.fontSize, 16, 36),
    fontWeight: cleanFontWeight(raw.fontWeight, defaultDashboardHero.fontWeight),
    letterSpacing: cleanLetterSpacing(raw.letterSpacing, defaultDashboardHero.letterSpacing),
    durationMs: cleanInt(raw.durationMs, defaultDashboardHero.durationMs, 100, 30000),
    pauseMs: cleanInt(raw.pauseMs, defaultDashboardHero.pauseMs, 0, 10000),
    color: cleanSvgColor(raw.color, defaultDashboardHero.color),
    backgroundColor: cleanSvgColor(raw.backgroundColor, defaultDashboardHero.backgroundColor, true),
    centered: typeof raw.centered === 'boolean' ? raw.centered : defaultDashboardHero.centered,
    verticalCentered: typeof raw.verticalCentered === 'boolean' ? raw.verticalCentered : defaultDashboardHero.verticalCentered,
    multiline: typeof raw.multiline === 'boolean' ? raw.multiline : defaultDashboardHero.multiline,
    repeat: typeof raw.repeat === 'boolean' ? raw.repeat : defaultDashboardHero.repeat,
    random: typeof raw.random === 'boolean' ? raw.random : defaultDashboardHero.random,
    width: cleanInt(raw.width, defaultDashboardHero.width, 160, 1600),
    height: cleanInt(raw.height, defaultDashboardHero.height, 30, 420),
  };
}

export function normalizeLayoutFooter(value: unknown): LayoutFooterConfig {
  const raw = isRecord(value) ? value : {};
  return {
    enabled: typeof raw.enabled === 'boolean' ? raw.enabled : defaultLayoutFooter.enabled,
    textTemplate: cleanText(raw.textTemplate, defaultLayoutFooter.textTemplate, 220),
    linkText: cleanOptionalText(raw.linkText, 80),
    linkUrl: cleanUrl(raw.linkUrl, '', true),
    fontSize: cleanInt(raw.fontSize, defaultLayoutFooter.fontSize, 10, 18),
    color: cleanColor(raw.color, defaultLayoutFooter.color),
  };
}

export function normalizeLoginContent(value: unknown): LoginContentConfig {
  const raw = isRecord(value) ? value : {};
  return {
    badgeTemplate: cleanText(raw.badgeTemplate, defaultLoginContent.badgeTemplate, 160),
    title: cleanText(raw.title, defaultLoginContent.title, 80),
    description: cleanText(raw.description, defaultLoginContent.description, 260),
    copyrightTemplate: cleanText(raw.copyrightTemplate, defaultLoginContent.copyrightTemplate, 160),
  };
}

export function buildTimeGreeting(hour: number) {
  if (hour >= 5 && hour < 9) return '早上好';
  if (hour >= 9 && hour < 12) return '上午好';
  if (hour >= 12 && hour < 14) return '中午好';
  if (hour >= 14 && hour < 18) return '下午好';
  return '晚上好';
}

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function formatDateValue(value: Date) {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

function formatTimeValue(value: Date) {
  return `${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`;
}

export function buildTemplateVariables(input: TemplateVariableInput): TemplateVariables {
  const now = input.now ?? new Date();
  const user = input.user ?? null;
  const site = input.siteIdentity;
  const weekday = ['日', '一', '二', '三', '四', '五', '六'][now.getDay()];
  return {
    appName: site.appName,
    appShortName: site.appShortName,
    appSubtitle: site.appSubtitle,
    username: user?.username ?? '',
    displayName: user?.displayName || user?.first_name || user?.username || site.appShortName,
    greeting: buildTimeGreeting(now.getHours()),
    date: formatDateValue(now),
    time: formatTimeValue(now),
    weekday: `星期${weekday}`,
    year: String(now.getFullYear()),
    localIp: input.localIp ?? '',
    generatedAt: input.generatedAt ?? '',
  };
}

export function renderTemplate(template: string, variables: TemplateVariables) {
  return template.replace(/\{([A-Za-z][A-Za-z0-9]*)\}/g, (match, key: string) => {
    if (!Object.prototype.hasOwnProperty.call(variables, key)) return match;
    const value = variables[key as keyof TemplateVariables];
    return value === undefined ? match : value;
  });
}

function svgColorParam(value: string) {
  return value.replace(/^#/, '').toUpperCase();
}

export function buildReadmeTypingSvgUrl(config: DashboardHeroConfig, lines: string[]) {
  const normalizedLines = lines.map((line) => line.trim()).filter(Boolean);
  const params = new URLSearchParams();
  params.set('font', config.font);
  params.set('weight', String(config.fontWeight));
  params.set('size', String(config.fontSize));
  params.set('letterSpacing', config.letterSpacing);
  params.set('duration', String(config.durationMs));
  params.set('pause', String(config.pauseMs));
  params.set('color', svgColorParam(config.color));
  params.set('background', svgColorParam(config.backgroundColor));
  params.set('center', String(config.centered));
  params.set('vCenter', String(config.verticalCentered));
  params.set('multiline', String(config.multiline));
  params.set('repeat', String(config.repeat));
  params.set('random', String(config.random));
  params.set('width', String(config.width));
  params.set('height', String(config.height));
  params.set('lines', normalizedLines.length ? normalizedLines.join(';') : ' ');
  return `${README_TYPING_SVG_URL}?${params.toString()}`;
}

function cloneConfig<T>(config: T): T {
  return JSON.parse(JSON.stringify(config)) as T;
}

export function useSiteSettings(feedback: SiteSettingsFeedback = {}) {
  const siteIdentity = ref<SiteIdentityConfig>(cloneConfig(defaultSiteIdentity));
  const dashboardHero = ref<DashboardHeroConfig>(cloneConfig(defaultDashboardHero));
  const layoutFooter = ref<LayoutFooterConfig>(cloneConfig(defaultLayoutFooter));
  const loginContent = ref<LoginContentConfig>(cloneConfig(defaultLoginContent));
  const uiTheme = ref<UiThemeConfig>(cloneConfig(defaultUiTheme));

  const siteIdentityDraft = ref<SiteIdentityConfig>(cloneConfig(defaultSiteIdentity));
  const dashboardHeroDraft = ref<DashboardHeroConfig>(cloneConfig(defaultDashboardHero));
  const layoutFooterDraft = ref<LayoutFooterConfig>(cloneConfig(defaultLayoutFooter));
  const loginContentDraft = ref<LoginContentConfig>(cloneConfig(defaultLoginContent));
  const uiThemeDraft = ref<UiThemeConfig>(cloneConfig(defaultUiTheme));

  const siteSettingsLoading = ref(false);
  const siteSettingsSaving = ref(false);
  const siteSettingsMessage = ref('');
  const existsByKey = ref<Record<string, boolean>>({
    [SITE_IDENTITY_SETTING_KEY]: false,
    [DASHBOARD_HERO_SETTING_KEY]: false,
    [LAYOUT_FOOTER_SETTING_KEY]: false,
    [LOGIN_CONTENT_SETTING_KEY]: false,
    [UI_THEME_SETTING_KEY]: false,
  });

  function applySetting(setting: SystemSetting | null, key: string) {
    existsByKey.value[key] = Boolean(setting);
    if (key === SITE_IDENTITY_SETTING_KEY) {
      siteIdentity.value = normalizeSiteIdentity(setting?.value);
      siteIdentityDraft.value = cloneConfig(siteIdentity.value);
    } else if (key === DASHBOARD_HERO_SETTING_KEY) {
      dashboardHero.value = normalizeDashboardHero(setting?.value);
      dashboardHeroDraft.value = cloneConfig(dashboardHero.value);
    } else if (key === LAYOUT_FOOTER_SETTING_KEY) {
      layoutFooter.value = normalizeLayoutFooter(setting?.value);
      layoutFooterDraft.value = cloneConfig(layoutFooter.value);
    } else if (key === LOGIN_CONTENT_SETTING_KEY) {
      loginContent.value = normalizeLoginContent(setting?.value);
      loginContentDraft.value = cloneConfig(loginContent.value);
    } else if (key === UI_THEME_SETTING_KEY) {
      uiTheme.value = normalizeUiThemeConfig(setting?.value);
      uiThemeDraft.value = cloneConfig(uiTheme.value);
    }
  }

  async function loadKeys(keys: string[]) {
    siteSettingsLoading.value = true;
    siteSettingsMessage.value = '';
    const results = await Promise.allSettled(keys.map((key) => getSystemSettingOrNull(key)));
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') applySetting(result.value, keys[index]);
    });
    const failed = results.find((result) => result.status === 'rejected') as PromiseRejectedResult | undefined;
    if (failed) {
      siteSettingsMessage.value = failed.reason instanceof Error ? failed.reason.message : '界面变量加载失败';
    }
    siteSettingsLoading.value = false;
  }

  async function loadPublicSiteSettings() {
    await loadKeys([SITE_IDENTITY_SETTING_KEY, LOGIN_CONTENT_SETTING_KEY, UI_THEME_SETTING_KEY]);
  }

  async function loadSiteIdentitySetting() {
    await loadKeys([SITE_IDENTITY_SETTING_KEY]);
  }

  async function loadDashboardHeroSetting() {
    await loadKeys([DASHBOARD_HERO_SETTING_KEY]);
  }

  async function loadLayoutFooterSetting() {
    await loadKeys([LAYOUT_FOOTER_SETTING_KEY]);
  }

  async function loadLoginContentSetting() {
    await loadKeys([LOGIN_CONTENT_SETTING_KEY]);
  }

  async function loadUiThemeSetting() {
    await loadKeys([UI_THEME_SETTING_KEY]);
  }

  async function loadSiteSettings() {
    await loadKeys([SITE_IDENTITY_SETTING_KEY, DASHBOARD_HERO_SETTING_KEY, LAYOUT_FOOTER_SETTING_KEY, LOGIN_CONTENT_SETTING_KEY, UI_THEME_SETTING_KEY]);
  }

  async function upsertSetting(key: string, payload: SystemSettingPayload) {
    const setting = existsByKey.value[key] ? await updateSystemSetting(key, payload) : await createSystemSetting(payload);
    existsByKey.value[key] = true;
    applySetting(setting, key);
  }

  async function saveSiteSettings() {
    siteSettingsSaving.value = true;
    siteSettingsMessage.value = '';
    try {
      await upsertSetting(SITE_IDENTITY_SETTING_KEY, {
        key: SITE_IDENTITY_SETTING_KEY,
        label: '品牌变量',
        description: '全局品牌名称、Logo 与 2FA 发行方',
        value: normalizeSiteIdentity(siteIdentityDraft.value),
      });
      await upsertSetting(DASHBOARD_HERO_SETTING_KEY, {
        key: DASHBOARD_HERO_SETTING_KEY,
        label: '仪表盘动态文字',
        description: '仪表盘 Hero 动态文字与显示样式',
        value: normalizeDashboardHero(dashboardHeroDraft.value),
      });
      await upsertSetting(LAYOUT_FOOTER_SETTING_KEY, {
        key: LAYOUT_FOOTER_SETTING_KEY,
        label: '页脚配置',
        description: '工作台页脚文案与链接',
        value: normalizeLayoutFooter(layoutFooterDraft.value),
      });
      await upsertSetting(LOGIN_CONTENT_SETTING_KEY, {
        key: LOGIN_CONTENT_SETTING_KEY,
        label: '登录页文案',
        description: '登录页欢迎文案与版权',
        value: normalizeLoginContent(loginContentDraft.value),
      });
      await upsertSetting(UI_THEME_SETTING_KEY, {
        key: UI_THEME_SETTING_KEY,
        label: '界面主题',
        description: '登录页与工作区共享的全站专业主题配色',
        value: normalizeUiThemeConfig(uiThemeDraft.value),
      });
      feedback.showToast?.('界面变量已保存', '', 'success');
    } catch (error) {
      siteSettingsMessage.value = error instanceof Error ? error.message : '界面变量保存失败';
    } finally {
      siteSettingsSaving.value = false;
    }
  }

  async function saveSiteIdentitySetting() {
    siteSettingsSaving.value = true;
    siteSettingsMessage.value = '';
    try {
      await upsertSetting(SITE_IDENTITY_SETTING_KEY, {
        key: SITE_IDENTITY_SETTING_KEY,
        label: '品牌变量',
        description: '全局品牌名称、Logo 与 2FA 发行方',
        value: normalizeSiteIdentity(siteIdentityDraft.value),
      });
      feedback.showToast?.('品牌变量已保存', '', 'success');
    } catch (error) {
      siteSettingsMessage.value = error instanceof Error ? error.message : '品牌变量保存失败';
    } finally {
      siteSettingsSaving.value = false;
    }
  }

  async function saveDashboardHeroSetting() {
    siteSettingsSaving.value = true;
    siteSettingsMessage.value = '';
    try {
      await upsertSetting(DASHBOARD_HERO_SETTING_KEY, {
        key: DASHBOARD_HERO_SETTING_KEY,
        label: '仪表盘动态文字',
        description: '仪表盘 Hero 动态文字与显示样式',
        value: normalizeDashboardHero(dashboardHeroDraft.value),
      });
      feedback.showToast?.('仪表盘动态文字已保存', '', 'success');
    } catch (error) {
      siteSettingsMessage.value = error instanceof Error ? error.message : '仪表盘动态文字保存失败';
    } finally {
      siteSettingsSaving.value = false;
    }
  }

  async function saveLayoutFooterSetting() {
    siteSettingsSaving.value = true;
    siteSettingsMessage.value = '';
    try {
      await upsertSetting(LAYOUT_FOOTER_SETTING_KEY, {
        key: LAYOUT_FOOTER_SETTING_KEY,
        label: '页脚配置',
        description: '工作台页脚文案与链接',
        value: normalizeLayoutFooter(layoutFooterDraft.value),
      });
      feedback.showToast?.('页脚配置已保存', '', 'success');
    } catch (error) {
      siteSettingsMessage.value = error instanceof Error ? error.message : '页脚配置保存失败';
    } finally {
      siteSettingsSaving.value = false;
    }
  }

  async function saveLoginContentSetting() {
    siteSettingsSaving.value = true;
    siteSettingsMessage.value = '';
    try {
      await upsertSetting(LOGIN_CONTENT_SETTING_KEY, {
        key: LOGIN_CONTENT_SETTING_KEY,
        label: '登录页文案',
        description: '登录页欢迎文案与版权',
        value: normalizeLoginContent(loginContentDraft.value),
      });
      feedback.showToast?.('登录页文案已保存', '', 'success');
    } catch (error) {
      siteSettingsMessage.value = error instanceof Error ? error.message : '登录页文案保存失败';
    } finally {
      siteSettingsSaving.value = false;
    }
  }

  async function saveUiThemeSetting() {
    siteSettingsSaving.value = true;
    siteSettingsMessage.value = '';
    try {
      await upsertSetting(UI_THEME_SETTING_KEY, {
        key: UI_THEME_SETTING_KEY,
        label: '界面主题',
        description: '登录页与工作区共享的全站专业主题配色',
        value: normalizeUiThemeConfig(uiThemeDraft.value),
      });
      feedback.showToast?.('界面主题已保存', '', 'success');
    } catch (error) {
      siteSettingsMessage.value = error instanceof Error ? error.message : '界面主题保存失败';
    } finally {
      siteSettingsSaving.value = false;
    }
  }

  function resetSiteSettingsDraft() {
    siteIdentityDraft.value = cloneConfig(siteIdentity.value);
    dashboardHeroDraft.value = cloneConfig(dashboardHero.value);
    layoutFooterDraft.value = cloneConfig(layoutFooter.value);
    loginContentDraft.value = cloneConfig(loginContent.value);
    uiThemeDraft.value = cloneConfig(uiTheme.value);
    siteSettingsMessage.value = '';
  }

  function resetSiteIdentityDraft() {
    siteIdentityDraft.value = cloneConfig(siteIdentity.value);
    siteSettingsMessage.value = '';
  }

  function resetDashboardHeroDraft() {
    dashboardHeroDraft.value = cloneConfig(dashboardHero.value);
    siteSettingsMessage.value = '';
  }

  function resetLayoutFooterDraft() {
    layoutFooterDraft.value = cloneConfig(layoutFooter.value);
    siteSettingsMessage.value = '';
  }

  function resetLoginContentDraft() {
    loginContentDraft.value = cloneConfig(loginContent.value);
    siteSettingsMessage.value = '';
  }

  function resetUiThemeDraft() {
    uiThemeDraft.value = cloneConfig(uiTheme.value);
    siteSettingsMessage.value = '';
  }

  return {
    siteIdentity,
    dashboardHero,
    layoutFooter,
    loginContent,
    uiTheme,
    siteIdentityDraft,
    dashboardHeroDraft,
    layoutFooterDraft,
    loginContentDraft,
    uiThemeDraft,
    siteSettingsLoading,
    siteSettingsSaving,
    siteSettingsMessage,
    loadPublicSiteSettings,
    loadSiteIdentitySetting,
    loadDashboardHeroSetting,
    loadLayoutFooterSetting,
    loadLoginContentSetting,
    loadUiThemeSetting,
    loadSiteSettings,
    saveSiteIdentitySetting,
    saveDashboardHeroSetting,
    saveLayoutFooterSetting,
    saveLoginContentSetting,
    saveUiThemeSetting,
    saveSiteSettings,
    resetSiteIdentityDraft,
    resetDashboardHeroDraft,
    resetLayoutFooterDraft,
    resetLoginContentDraft,
    resetUiThemeDraft,
    resetSiteSettingsDraft,
  };
}
