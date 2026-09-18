<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import { useAppContext } from '@app/context';
import {
  buildReadmeTypingSvgUrl,
  buildTemplateVariables,
  dashboardHeroFontOptions,
  dashboardHeroLetterSpacingOptions,
  renderTemplate,
} from '../../composables/features/useSiteSettings';
import { watermarkPageGroups } from '../../composables/features/useWatermarkSettings';
import { createSystemSetting, getSystemSettingOrNull, updateSystemSetting } from '../../services/system';
import { createDefaultTerminalSettings, normalizeTerminalSettings } from '../../utils/terminalSettings';
import { buildUiThemePalette, normalizeHexColor, normalizeUiThemeConfig, uiThemePresetOptions } from '../../utils/uiTheme';
import AppIcon from '@shared/components/AppIcon.vue';
import WatermarkOverlay from '@shared/components/WatermarkOverlay.vue';
import type { AuthSessionConfig, LogRetentionConfig, TerminalSettingsConfig } from '../../types';

type SettingsTabKey = 'system' | 'dashboard' | 'logRetention' | 'securityScan' | 'watermark' | 'terminal';
type SettingsTabIcon = 'settings' | 'dashboard' | 'rows' | 'image' | 'shield' | 'terminal';
type LoginExpiryUnit = 'minutes' | 'hours' | 'days';
const AUTH_SESSION_SETTING_KEY = 'auth_session';
const LOG_RETENTION_SETTING_KEY = 'log_retention';
const SECURITY_SCAN_SETTING_KEY = 'security_scan';
const TERMINAL_SETTINGS_SETTING_KEY = 'terminal_settings';
const defaultAuthSession: AuthSessionConfig = { loginExpiryMinutes: 480 };
const defaultLogRetention: LogRetentionConfig = {
  loginLogsDays: 180,
  operationLogsDays: 180,
  terminalCommandAuditDays: 180,
  terminalFileAuditDays: 180,
  terminalSessionDays: 180,
  rdpRecordingEnabled: false,
  rdpRecordingDays: 30,
};
const defaultTerminalSettings = createDefaultTerminalSettings();

const {
  siteIdentityDraft,
  dashboardHeroDraft,
  layoutFooterDraft,
  loginContentDraft,
  uiThemeDraft,
  siteSettingsLoading,
  siteSettingsSaving,
  siteSettingsMessage,
  loadSiteIdentitySetting,
  loadDashboardHeroSetting,
  loadLayoutFooterSetting,
  loadLoginContentSetting,
  loadUiThemeSetting,
  saveSiteIdentitySetting,
  saveDashboardHeroSetting,
  saveLayoutFooterSetting,
  saveLoginContentSetting,
  saveUiThemeSetting,
  resetSiteIdentityDraft,
  resetDashboardHeroDraft,
  resetLayoutFooterDraft,
  resetLoginContentDraft,
  resetUiThemeDraft,
  watermarkDraft,
  watermarkPreviewText,
  watermarkLoading,
  watermarkSaving,
  watermarkMessage,
  loadWatermarkSetting,
  saveWatermarkSetting,
  resetWatermarkDraft,
  currentUser,
  localIp,
  canUsePageAction,
  canUseAnyPageAction,
} = useAppContext();

const settingsTabs: Array<{ key: SettingsTabKey; label: string; title: string; subtitle: string; icon: SettingsTabIcon }> = [
  { key: 'system', label: '系统设置', title: '系统设置', subtitle: '品牌、登录页、页脚与登录会话', icon: 'settings' },
  { key: 'dashboard', label: '仪表盘', title: '仪表盘动态文字', subtitle: 'Hero 文案、样式与打字动画', icon: 'dashboard' },
  { key: 'logRetention', label: '日志保留', title: '日志保留', subtitle: '统一管理审计日志和 RDP 录像留存', icon: 'rows' },
  { key: 'securityScan', label: '安全扫描', title: '安全扫描', subtitle: '在线漏洞源访问开关', icon: 'shield' },
  { key: 'watermark', label: '水印', title: '水印配置', subtitle: '水印模板与应用页面', icon: 'image' },
  { key: 'terminal', label: '终端', title: '终端设置', subtitle: 'Web SSH 连接、保活、显示默认值与批量执行', icon: 'terminal' },
];

const activeTab = ref<SettingsTabKey>('system');
const authSessionConfig = ref<AuthSessionConfig>({ ...defaultAuthSession });
const authSessionDraft = ref<AuthSessionConfig>({ ...defaultAuthSession });
const authSessionSettingExists = ref(false);
const authSessionLoading = ref(false);
const authSessionSaving = ref(false);
const authSessionMessage = ref('');
const loginExpiryValue = ref(8);
const loginExpiryUnit = ref<LoginExpiryUnit>('hours');
const logRetentionDraft = ref<LogRetentionConfig>({ ...defaultLogRetention });
const logRetentionSettingExists = ref(false);
const logRetentionLoading = ref(false);
const logRetentionSaving = ref(false);
const logRetentionMessage = ref('');
const securityScanDraft = ref({ onlineCveEnabled: false });
const securityScanSettingExists = ref(false);
const securityScanLoading = ref(false);
const securityScanSaving = ref(false);
const securityScanMessage = ref('');
const terminalSettingsDraft = ref<TerminalSettingsConfig>({ ...defaultTerminalSettings });
const terminalSettingsSettingExists = ref(false);
const terminalSettingsLoading = ref(false);
const terminalSettingsSaving = ref(false);
const terminalSettingsMessage = ref('');
const canSave = computed(() => canUsePageAction('systemSettings', 'save'));
const currentTab = computed(() => settingsTabs.find((tab) => tab.key === activeTab.value) ?? settingsTabs[0]);
const currentBusy = computed(() =>
  activeTab.value === 'system'
    ? siteSettingsSaving.value || authSessionSaving.value
    : activeTab.value === 'watermark'
    ? watermarkSaving.value
    : activeTab.value === 'logRetention'
      ? logRetentionSaving.value
      : activeTab.value === 'securityScan'
        ? securityScanSaving.value
        : activeTab.value === 'terminal'
          ? terminalSettingsSaving.value
          : siteSettingsSaving.value,
);
const currentLoading = computed(() =>
  activeTab.value === 'system'
    ? siteSettingsLoading.value || authSessionLoading.value
    : activeTab.value === 'watermark'
    ? watermarkLoading.value
    : activeTab.value === 'logRetention'
      ? logRetentionLoading.value
      : activeTab.value === 'securityScan'
        ? securityScanLoading.value
        : activeTab.value === 'terminal'
          ? terminalSettingsLoading.value
          : siteSettingsLoading.value,
);
const currentMessage = computed(() =>
  activeTab.value === 'system'
    ? siteSettingsMessage.value || authSessionMessage.value
    : activeTab.value === 'watermark'
    ? watermarkMessage.value
    : activeTab.value === 'logRetention'
      ? logRetentionMessage.value
      : activeTab.value === 'securityScan'
        ? securityScanMessage.value
        : activeTab.value === 'terminal'
          ? terminalSettingsMessage.value
          : siteSettingsMessage.value,
);
const selectedPages = computed(() => new Set(watermarkDraft.value.pages));
const allPageKeys = computed(() => watermarkPageGroups.flatMap((group) => group.pages.map((page) => page.key)));
const previewVariables = computed(() =>
  buildTemplateVariables({
    siteIdentity: siteIdentityDraft.value,
    user: currentUser.value,
    localIp: localIp.value,
    generatedAt: '2026-07-01 12:00',
  }),
);
const previewHeroBadge = computed(() => renderTemplate(dashboardHeroDraft.value.badgeTemplate, previewVariables.value));
const previewHeroLines = computed(() =>
  [dashboardHeroDraft.value.line1Template, dashboardHeroDraft.value.line2Template]
    .map((template) => renderTemplate(template, previewVariables.value))
    .filter(Boolean),
);
const previewHeroSvgUrl = computed(() => buildReadmeTypingSvgUrl(dashboardHeroDraft.value, previewHeroLines.value));
const previewDescription = computed(() => renderTemplate(dashboardHeroDraft.value.descriptionTemplate, previewVariables.value));
const previewFooterText = computed(() => renderTemplate(layoutFooterDraft.value.textTemplate, previewVariables.value));
const previewFooterLink = computed(() => renderTemplate(layoutFooterDraft.value.linkText, previewVariables.value));
const previewLoginBadge = computed(() => renderTemplate(loginContentDraft.value.badgeTemplate, previewVariables.value));
const previewLoginTitle = computed(() => renderTemplate(loginContentDraft.value.title, previewVariables.value));
const previewLoginDescription = computed(() => renderTemplate(loginContentDraft.value.description, previewVariables.value));
const previewLoginCopyright = computed(() => renderTemplate(loginContentDraft.value.copyrightTemplate, previewVariables.value));
const themePreviewPalette = computed(() => buildUiThemePalette(normalizeUiThemeConfig(uiThemeDraft.value)));
const themePreviewStyle = computed(() => ({
  '--theme-preview-primary-light': themePreviewPalette.value.lightPrimary,
  '--theme-preview-primary-dark': themePreviewPalette.value.darkPrimary,
  '--theme-preview-primary-foreground-light': themePreviewPalette.value.lightPrimaryForeground,
  '--theme-preview-primary-foreground-dark': themePreviewPalette.value.darkPrimaryForeground,
}));
const loginExpiryInputMax = computed(() => {
  if (loginExpiryUnit.value === 'days') return 30;
  if (loginExpiryUnit.value === 'hours') return 720;
  return 43200;
});

function normalizeAuthSession(value: unknown): AuthSessionConfig {
  const raw = typeof value === 'object' && value !== null ? (value as Partial<AuthSessionConfig>) : {};
  const minutes = Number(raw.loginExpiryMinutes);
  return {
    loginExpiryMinutes: Number.isInteger(minutes) ? Math.min(43200, Math.max(1, minutes)) : defaultAuthSession.loginExpiryMinutes,
  };
}

function syncAuthSessionDisplay() {
  const minutes = authSessionDraft.value.loginExpiryMinutes;
  if (minutes % 1440 === 0) {
    loginExpiryValue.value = minutes / 1440;
    loginExpiryUnit.value = 'days';
  } else if (minutes % 60 === 0) {
    loginExpiryValue.value = minutes / 60;
    loginExpiryUnit.value = 'hours';
  } else {
    loginExpiryValue.value = minutes;
    loginExpiryUnit.value = 'minutes';
  }
}

function authSessionMinutesFromDisplay() {
  const value = Math.max(1, Math.round(Number(loginExpiryValue.value) || 1));
  const multiplier = loginExpiryUnit.value === 'days' ? 1440 : loginExpiryUnit.value === 'hours' ? 60 : 1;
  return Math.min(43200, Math.max(1, value * multiplier));
}

async function loadAuthSessionSetting() {
  authSessionLoading.value = true;
  authSessionMessage.value = '';
  try {
    const setting = await getSystemSettingOrNull(AUTH_SESSION_SETTING_KEY);
    authSessionSettingExists.value = Boolean(setting);
    authSessionConfig.value = normalizeAuthSession(setting?.value);
    authSessionDraft.value = { ...authSessionConfig.value };
    syncAuthSessionDisplay();
  } catch (error) {
    authSessionMessage.value = error instanceof Error ? error.message : '登录会话设置加载失败';
  } finally {
    authSessionLoading.value = false;
  }
}

async function loadSystemSettings() {
  await Promise.all([
    loadSiteIdentitySetting(),
    loadLoginContentSetting(),
    loadUiThemeSetting(),
    loadLayoutFooterSetting(),
    loadAuthSessionSetting(),
  ]);
}

async function saveAuthSessionSetting() {
  authSessionSaving.value = true;
  authSessionMessage.value = '';
  const normalized = { loginExpiryMinutes: authSessionMinutesFromDisplay() };
  const payload = {
    key: AUTH_SESSION_SETTING_KEY,
    label: '登录会话',
    description: '统一控制系统登录和 Web 终端会话过期时间',
    value: normalized,
  };
  try {
    const setting = authSessionSettingExists.value
      ? await updateSystemSetting(AUTH_SESSION_SETTING_KEY, payload)
      : await createSystemSetting(payload);
    authSessionSettingExists.value = true;
    authSessionConfig.value = normalizeAuthSession(setting.value);
    authSessionDraft.value = { ...authSessionConfig.value };
    syncAuthSessionDisplay();
    authSessionMessage.value = '登录会话设置已保存';
  } catch (error) {
    authSessionMessage.value = error instanceof Error ? error.message : '登录会话设置保存失败';
  } finally {
    authSessionSaving.value = false;
  }
}

async function saveSystemSettings() {
  await saveSiteIdentitySetting();
  await saveLoginContentSetting();
  await saveLayoutFooterSetting();
  await saveUiThemeSetting();
  await saveAuthSessionSetting();
}

function resetAuthSessionDraft() {
  authSessionDraft.value = { ...authSessionConfig.value };
  syncAuthSessionDisplay();
  authSessionMessage.value = '';
}

function resetSystemSettingsDraft() {
  resetSiteIdentityDraft();
  resetLoginContentDraft();
  resetLayoutFooterDraft();
  resetUiThemeDraft();
  resetAuthSessionDraft();
}

function selectThemePreset(preset: typeof uiThemeDraft.value.preset) {
  if (!canSave.value) return;
  uiThemeDraft.value.preset = preset;
}

function normalizeCustomPrimary() {
  uiThemeDraft.value.customPrimary = normalizeHexColor(uiThemeDraft.value.customPrimary);
}

async function refreshCurrentTab() {
  if (currentLoading.value) return;
  if (activeTab.value === 'system') await loadSystemSettings();
  else if (activeTab.value === 'dashboard') await loadDashboardHeroSetting();
  else if (activeTab.value === 'logRetention') await loadLogRetentionSetting();
  else if (activeTab.value === 'securityScan') await loadSecurityScanSetting();
  else if (activeTab.value === 'terminal') await loadTerminalSettingsSetting();
  else await loadWatermarkSetting();
}

async function saveCurrentTab() {
  if (!canSave.value || currentBusy.value) return;
  if (activeTab.value === 'system') await saveSystemSettings();
  else if (activeTab.value === 'dashboard') await saveDashboardHeroSetting();
  else if (activeTab.value === 'logRetention') await saveLogRetentionSetting();
  else if (activeTab.value === 'securityScan') await saveSecurityScanSetting();
  else if (activeTab.value === 'terminal') await saveTerminalSettingsSetting();
  else await saveWatermarkSetting();
}

function resetCurrentTab() {
  if (activeTab.value === 'system') resetSystemSettingsDraft();
  else if (activeTab.value === 'dashboard') resetDashboardHeroDraft();
  else if (activeTab.value === 'logRetention') resetLogRetentionDraft();
  else if (activeTab.value === 'securityScan') resetSecurityScanDraft();
  else if (activeTab.value === 'terminal') resetTerminalSettingsDraft();
  else resetWatermarkDraft();
}

function normalizeRetentionDays(value: unknown, fallback: number) {
  const number = Number(value);
  if (!Number.isInteger(number)) return fallback;
  return Math.min(3650, Math.max(0, number));
}

function normalizeLogRetention(value: unknown): LogRetentionConfig {
  const raw = typeof value === 'object' && value !== null ? (value as Partial<LogRetentionConfig>) : {};
  return {
    loginLogsDays: normalizeRetentionDays(raw.loginLogsDays, defaultLogRetention.loginLogsDays),
    operationLogsDays: normalizeRetentionDays(raw.operationLogsDays, defaultLogRetention.operationLogsDays),
    terminalCommandAuditDays: normalizeRetentionDays(raw.terminalCommandAuditDays, defaultLogRetention.terminalCommandAuditDays),
    terminalFileAuditDays: normalizeRetentionDays(raw.terminalFileAuditDays, defaultLogRetention.terminalFileAuditDays),
    terminalSessionDays: normalizeRetentionDays(raw.terminalSessionDays, defaultLogRetention.terminalSessionDays),
    rdpRecordingEnabled: typeof raw.rdpRecordingEnabled === 'boolean' ? raw.rdpRecordingEnabled : defaultLogRetention.rdpRecordingEnabled,
    rdpRecordingDays: normalizeRetentionDays(raw.rdpRecordingDays, defaultLogRetention.rdpRecordingDays),
  };
}

async function loadLogRetentionSetting() {
  logRetentionLoading.value = true;
  logRetentionMessage.value = '';
  try {
    const setting = await getSystemSettingOrNull(LOG_RETENTION_SETTING_KEY);
    logRetentionSettingExists.value = Boolean(setting);
    logRetentionDraft.value = normalizeLogRetention(setting?.value);
  } catch (error) {
    logRetentionMessage.value = error instanceof Error ? error.message : '日志保留设置加载失败';
  } finally {
    logRetentionLoading.value = false;
  }
}

async function saveLogRetentionSetting() {
  logRetentionSaving.value = true;
  logRetentionMessage.value = '';
  const normalized = normalizeLogRetention(logRetentionDraft.value);
  const payload = {
    key: LOG_RETENTION_SETTING_KEY,
    label: '日志保留',
    description: '统一管理登录日志、操作日志、终端审计和 RDP 录像留存策略',
    value: {
      loginLogsDays: normalized.loginLogsDays,
      operationLogsDays: normalized.operationLogsDays,
      terminalCommandAuditDays: normalized.terminalCommandAuditDays,
      terminalFileAuditDays: normalized.terminalFileAuditDays,
      terminalSessionDays: normalized.terminalSessionDays,
      rdpRecordingEnabled: normalized.rdpRecordingEnabled,
      rdpRecordingDays: normalized.rdpRecordingDays,
    },
  };
  try {
    const setting = logRetentionSettingExists.value
      ? await updateSystemSetting(LOG_RETENTION_SETTING_KEY, payload)
      : await createSystemSetting(payload);
    logRetentionSettingExists.value = true;
    logRetentionDraft.value = normalizeLogRetention(setting.value);
    logRetentionMessage.value = '日志保留设置已保存';
  } catch (error) {
    logRetentionMessage.value = error instanceof Error ? error.message : '日志保留设置保存失败';
  } finally {
    logRetentionSaving.value = false;
  }
}

function resetLogRetentionDraft() {
  logRetentionDraft.value = { ...defaultLogRetention };
  logRetentionMessage.value = '';
}

async function loadSecurityScanSetting() {
  securityScanLoading.value = true;
  securityScanMessage.value = '';
  try {
    const setting = await getSystemSettingOrNull(SECURITY_SCAN_SETTING_KEY);
    securityScanSettingExists.value = Boolean(setting);
    const value = setting?.value as { onlineCveEnabled?: unknown } | undefined;
    securityScanDraft.value = { onlineCveEnabled: Boolean(value?.onlineCveEnabled) };
  } catch (error) {
    securityScanMessage.value = error instanceof Error ? error.message : '安全扫描设置加载失败';
  } finally {
    securityScanLoading.value = false;
  }
}

async function saveSecurityScanSetting() {
  securityScanSaving.value = true;
  securityScanMessage.value = '';
  const payload = {
    key: SECURITY_SCAN_SETTING_KEY,
    label: '安全扫描',
    description: '控制安全扫描是否访问 OSV/NVD 在线漏洞源',
    value: { onlineCveEnabled: Boolean(securityScanDraft.value.onlineCveEnabled) },
  };
  try {
    const setting = securityScanSettingExists.value
      ? await updateSystemSetting(SECURITY_SCAN_SETTING_KEY, payload)
      : await createSystemSetting(payload);
    securityScanSettingExists.value = true;
    const value = setting.value as { onlineCveEnabled?: unknown };
    securityScanDraft.value = { onlineCveEnabled: Boolean(value.onlineCveEnabled) };
    securityScanMessage.value = '安全扫描设置已保存';
  } catch (error) {
    securityScanMessage.value = error instanceof Error ? error.message : '安全扫描设置保存失败';
  } finally {
    securityScanSaving.value = false;
  }
}

function resetSecurityScanDraft() {
  securityScanDraft.value = { onlineCveEnabled: false };
  securityScanMessage.value = '';
}

async function loadTerminalSettingsSetting() {
  terminalSettingsLoading.value = true;
  terminalSettingsMessage.value = '';
  try {
    const setting = await getSystemSettingOrNull(TERMINAL_SETTINGS_SETTING_KEY);
    terminalSettingsSettingExists.value = Boolean(setting);
    terminalSettingsDraft.value = normalizeTerminalSettings(setting?.value);
  } catch (error) {
    terminalSettingsMessage.value = error instanceof Error ? error.message : '终端设置加载失败';
  } finally {
    terminalSettingsLoading.value = false;
  }
}

async function saveTerminalSettingsSetting() {
  terminalSettingsSaving.value = true;
  terminalSettingsMessage.value = '';
  const normalized = normalizeTerminalSettings(terminalSettingsDraft.value);
  const payload = {
    key: TERMINAL_SETTINGS_SETTING_KEY,
    label: '终端设置',
    description: 'Web SSH 连接、保活、读取和显示默认值',
    value: normalized,
  };
  try {
    const setting = terminalSettingsSettingExists.value
      ? await updateSystemSetting(TERMINAL_SETTINGS_SETTING_KEY, payload)
      : await createSystemSetting(payload);
    terminalSettingsSettingExists.value = true;
    terminalSettingsDraft.value = normalizeTerminalSettings(setting.value);
    terminalSettingsMessage.value = '终端设置已保存';
  } catch (error) {
    terminalSettingsMessage.value = error instanceof Error ? error.message : '终端设置保存失败';
  } finally {
    terminalSettingsSaving.value = false;
  }
}

function resetTerminalSettingsDraft() {
  terminalSettingsDraft.value = { ...defaultTerminalSettings };
  terminalSettingsMessage.value = '';
}

function toggleWatermarkPage(page: string) {
  if (!canSave.value) return;
  const next = new Set(watermarkDraft.value.pages);
  if (next.has(page)) {
    next.delete(page);
  } else {
    next.add(page);
  }
  watermarkDraft.value.pages = [...next];
}

function toggleAllWatermarkPages() {
  if (!canSave.value) return;
  watermarkDraft.value.pages = watermarkDraft.value.pages.length === allPageKeys.value.length ? [] : [...allPageKeys.value];
}

onMounted(() => {
  void loadSystemSettings();
  void loadLogRetentionSetting();
  void loadSecurityScanSetting();
  void loadTerminalSettingsSetting();
});
</script>

<template>
  <section class="system-settings-page">
    <template v-if="canUseAnyPageAction('systemSettings', ['save', 'reset', 'refresh'])">
      <article class="system-settings-main">
        <header class="system-settings-title">
          <div>
            <h2>界面变量配置</h2>
            <p>{{ currentTab.subtitle }}</p>
          </div>
          <div class="system-settings-actions">
            <el-button v-if="canUsePageAction('systemSettings', 'refresh')" :disabled="currentLoading" @click="refreshCurrentTab">
              <AppIcon name="refresh" :size="15" />刷新
            </el-button>
            <el-button v-if="canUsePageAction('systemSettings', 'reset')" :disabled="currentBusy" @click="resetCurrentTab">
              <AppIcon name="reset" :size="15" />还原
            </el-button>
            <el-button v-if="canSave" type="primary" :disabled="currentBusy" @click="saveCurrentTab">
              {{ currentBusy ? '保存中...' : '保存当前' }}
            </el-button>
          </div>
        </header>

        <nav class="system-settings-tabs" aria-label="系统设置分类">
          <el-button
            v-for="tab in settingsTabs"
            :key="tab.key"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            <AppIcon :name="tab.icon" :size="16" />
            <span>{{ tab.label }}</span>
          </el-button>
        </nav>

        <p v-if="currentMessage" class="system-settings-message">{{ currentMessage }}</p>

        <section v-if="activeTab === 'system'" class="settings-section single merged-system-settings">
          <section class="theme-settings-card">
            <header>
              <h3>专业主题配色</h3>
              <span>登录页、工作区和弹层共享同一套语义色</span>
            </header>
            <div class="theme-preset-grid">
              <el-button
                v-for="option in uiThemePresetOptions"
                :key="option.value"
                type="button"
                class="theme-preset-card"
                :class="{ active: uiThemeDraft.preset === option.value }"
                :disabled="!canSave"
                @click="selectThemePreset(option.value)"
              >
                <span class="theme-preset-swatch" :style="{ backgroundColor: option.value === 'custom' ? uiThemeDraft.customPrimary : option.color }"></span>
                <strong>{{ option.label }}</strong>
                <small>{{ option.value === 'custom' ? uiThemeDraft.customPrimary : option.color }}</small>
                <AppIcon v-if="uiThemeDraft.preset === option.value" name="check" :size="15" />
              </el-button>
            </div>
            <div v-if="uiThemeDraft.preset === 'custom'" class="theme-custom-field">
              <el-color-picker v-model="uiThemeDraft.customPrimary" :disabled="!canSave" />
              <el-input
                v-model="uiThemeDraft.customPrimary"
                :disabled="!canSave"
                maxlength="7"
                placeholder="#2563EB"
                @blur="normalizeCustomPrimary"
              />
            </div>
            <div class="theme-preview-grid" :style="themePreviewStyle">
              <article class="theme-preview theme-preview-light">
                <span>Light</span>
                <strong>专业工作台</strong>
                <p>卡片、输入框、主按钮与焦点环预览</p>
                <div><i></i><el-button type="primary" size="small">主要操作</el-button></div>
              </article>
              <article class="theme-preview theme-preview-dark">
                <span>Dark</span>
                <strong>专业工作台</strong>
                <p>深色界面自动生成高对比主色</p>
                <div><i></i><el-button type="primary" size="small">主要操作</el-button></div>
              </article>
            </div>
          </section>

          <section>
            <header>
              <h3>品牌信息</h3>
              <span>全局品牌与 2FA 发行方</span>
            </header>
            <div class="settings-field-grid compact-settings-field-grid">
              <label>
                <span>应用名称</span>
                <el-input v-model="siteIdentityDraft.appName" :disabled="!canSave" maxlength="80" />
              </label>
              <label>
                <span>短名称</span>
                <el-input v-model="siteIdentityDraft.appShortName" :disabled="!canSave" maxlength="32" />
              </label>
              <label>
                <span>副标题</span>
                <el-input v-model="siteIdentityDraft.appSubtitle" :disabled="!canSave" maxlength="80" />
              </label>
              <label>
                <span>浏览器标题</span>
                <el-input v-model="siteIdentityDraft.browserTitle" :disabled="!canSave" maxlength="80" />
              </label>
              <label>
                <span>Logo 文本</span>
                <el-input v-model="siteIdentityDraft.logoText" :disabled="!canSave" maxlength="32" />
              </label>
              <label>
                <span>2FA 发行方</span>
                <el-input v-model="siteIdentityDraft.totpIssuer" :disabled="!canSave" maxlength="80" />
              </label>
              <label class="span-3">
                <span>Logo 图片地址</span>
                <el-input v-model="siteIdentityDraft.logoImageUrl" :disabled="!canSave" maxlength="500" />
              </label>
              <label class="span-3">
                <span>默认图标地址</span>
                <el-input v-model="siteIdentityDraft.iconUrl" :disabled="!canSave" maxlength="500" />
              </label>
            </div>
          </section>

          <section>
            <header>
              <h3>登录页</h3>
              <span>未登录页面展示内容</span>
            </header>
            <div class="settings-field-grid compact-settings-field-grid">
              <label>
                <span>徽标模板</span>
                <el-input v-model="loginContentDraft.badgeTemplate" :disabled="!canSave" maxlength="160" />
              </label>
              <label>
                <span>标题</span>
                <el-input v-model="loginContentDraft.title" :disabled="!canSave" maxlength="80" />
              </label>
              <label class="span-3">
                <span>说明文案</span>
                <el-input v-model="loginContentDraft.description" :disabled="!canSave" maxlength="260" type="textarea" :rows="4" />
              </label>
              <label class="span-3">
                <span>版权模板</span>
                <el-input v-model="loginContentDraft.copyrightTemplate" :disabled="!canSave" maxlength="160" />
              </label>
            </div>
          </section>

          <section>
            <header>
              <h3>页脚</h3>
              <span>底部文案、链接与显示样式</span>
            </header>
            <div class="settings-field-grid compact-settings-field-grid">
              <el-checkbox v-model="layoutFooterDraft.enabled" :disabled="!canSave" class="settings-check-row">显示页脚</el-checkbox>
              <label>
                <span>字号</span>
                <el-input-number v-model="layoutFooterDraft.fontSize" :disabled="!canSave" :min="10" :max="18" />
              </label>
              <label>
                <span>颜色</span>
                <el-color-picker v-model="layoutFooterDraft.color" :disabled="!canSave" />
              </label>
              <label class="span-3">
                <span>页脚模板</span>
                <el-input v-model="layoutFooterDraft.textTemplate" :disabled="!canSave" maxlength="220" />
              </label>
              <label>
                <span>链接文字</span>
                <el-input v-model="layoutFooterDraft.linkText" :disabled="!canSave" maxlength="80" />
              </label>
              <label class="span-2">
                <span>链接地址</span>
                <el-input v-model="layoutFooterDraft.linkUrl" :disabled="!canSave" maxlength="500" />
              </label>
            </div>
          </section>

          <section>
            <header>
              <h3>登录会话</h3>
              <span>过期后刷新需重新登录，Web 终端同步断开</span>
            </header>
            <div class="settings-field-grid compact-settings-field-grid">
              <label class="expiry-duration-field">
                <span>系统登录过期时间</span>
                <div>
                  <el-input-number v-model="loginExpiryValue" :disabled="!canSave" :min="1" :max="loginExpiryInputMax" />
                  <el-select v-model="loginExpiryUnit" :disabled="!canSave">
                    <el-option value="minutes" label="分钟" />
                    <el-option value="hours" label="小时" />
                    <el-option value="days" label="天" />
                  </el-select>
                </div>
              </label>
            </div>
          </section>
        </section>

        <section v-else-if="activeTab === 'dashboard'" class="settings-section single">
          <header>
            <h3>仪表盘动态文字</h3>
            <span>动态 SVG 参数</span>
          </header>
          <div class="settings-field-grid dashboard-hero-field-grid">
            <label>
              <span>徽标模板</span>
              <el-input v-model="dashboardHeroDraft.badgeTemplate" :disabled="!canSave" maxlength="160" />
            </label>
            <label>
              <span>第一行动画</span>
              <el-input v-model="dashboardHeroDraft.line1Template" :disabled="!canSave" maxlength="160" />
            </label>
            <label>
              <span>第二行动画</span>
              <el-input v-model="dashboardHeroDraft.line2Template" :disabled="!canSave" maxlength="160" />
            </label>
            <label class="span-4">
              <span>说明文案</span>
              <el-input v-model="dashboardHeroDraft.descriptionTemplate" :disabled="!canSave" maxlength="260" type="textarea" :rows="4" />
            </label>
            <label>
              <span>字体</span>
              <el-select v-model="dashboardHeroDraft.font" :disabled="!canSave">
                <el-option v-for="font in dashboardHeroFontOptions" :key="font" :value="font" :label="font" />
              </el-select>
            </label>
            <label>
              <span>字号</span>
              <el-input-number v-model="dashboardHeroDraft.fontSize" :disabled="!canSave" :min="16" :max="36" />
            </label>
            <label>
              <span>字体加粗</span>
              <el-select v-model="dashboardHeroDraft.fontWeight" :disabled="!canSave">
                <el-option :value="400" label="常规 400" />
                <el-option :value="500" label="中等 500" />
                <el-option :value="600" label="半粗 600" />
                <el-option :value="700" label="加粗 700" />
                <el-option :value="800" label="超粗 800" />
                <el-option :value="900" label="最粗 900" />
              </el-select>
            </label>
            <label>
              <span>字间距</span>
              <el-select v-model="dashboardHeroDraft.letterSpacing" :disabled="!canSave">
                <el-option v-for="spacing in dashboardHeroLetterSpacingOptions" :key="spacing.value" :value="spacing.value" :label="spacing.label" />
              </el-select>
            </label>
            <label>
              <span>每行持续时间 ms</span>
              <el-input-number v-model="dashboardHeroDraft.durationMs" :disabled="!canSave" :min="100" :max="30000" />
            </label>
            <label>
              <span>停顿时间 ms</span>
              <el-input-number v-model="dashboardHeroDraft.pauseMs" :disabled="!canSave" :min="0" :max="10000" />
            </label>
            <label>
              <span>文字颜色</span>
              <el-color-picker v-model="dashboardHeroDraft.color" :disabled="!canSave" />
            </label>
            <label>
              <span>背景颜色</span>
              <el-input v-model="dashboardHeroDraft.backgroundColor" :disabled="!canSave" maxlength="9" placeholder="#00000000" />
            </label>
            <el-checkbox v-model="dashboardHeroDraft.centered" :disabled="!canSave" class="settings-check-row">水平居中</el-checkbox>
            <el-checkbox v-model="dashboardHeroDraft.verticalCentered" :disabled="!canSave" class="settings-check-row">垂直居中</el-checkbox>
            <el-checkbox v-model="dashboardHeroDraft.multiline" :disabled="!canSave" class="settings-check-row">多行显示</el-checkbox>
            <el-checkbox v-model="dashboardHeroDraft.repeat" :disabled="!canSave" class="settings-check-row">循环播放</el-checkbox>
            <el-checkbox v-model="dashboardHeroDraft.random" :disabled="!canSave" class="settings-check-row">随机顺序</el-checkbox>
            <label>
              <span>宽度</span>
              <el-input-number v-model="dashboardHeroDraft.width" :disabled="!canSave" :min="160" :max="1600" />
            </label>
            <label>
              <span>高度</span>
              <el-input-number v-model="dashboardHeroDraft.height" :disabled="!canSave" :min="30" :max="420" />
            </label>
          </div>
        </section>

        <section v-else-if="activeTab === 'logRetention'" class="settings-section single">
          <header>
            <h3>日志保留</h3>
            <span>0 表示永久保留</span>
          </header>
          <div class="settings-field-grid log-retention-field-grid">
            <el-checkbox v-model="logRetentionDraft.rdpRecordingEnabled" :disabled="!canSave" class="settings-check-row">开启 RDP 录像</el-checkbox>
            <label>
              <span>登录日志保留天数</span>
              <el-input-number v-model="logRetentionDraft.loginLogsDays" :disabled="!canSave" :min="0" :max="3650" />
            </label>
            <label>
              <span>操作日志保留天数</span>
              <el-input-number v-model="logRetentionDraft.operationLogsDays" :disabled="!canSave" :min="0" :max="3650" />
            </label>
            <label>
              <span>终端命令审计保留天数</span>
              <el-input-number v-model="logRetentionDraft.terminalCommandAuditDays" :disabled="!canSave" :min="0" :max="3650" />
            </label>
            <label>
              <span>终端文件审计保留天数</span>
              <el-input-number v-model="logRetentionDraft.terminalFileAuditDays" :disabled="!canSave" :min="0" :max="3650" />
            </label>
            <label>
              <span>终端会话元数据保留天数</span>
              <el-input-number v-model="logRetentionDraft.terminalSessionDays" :disabled="!canSave" :min="0" :max="3650" />
            </label>
            <label>
              <span>RDP 录像文件保留天数</span>
              <el-input-number v-model="logRetentionDraft.rdpRecordingDays" :disabled="!canSave" :min="0" :max="3650" />
            </label>
          </div>
        </section>

        <section v-else-if="activeTab === 'securityScan'" class="settings-section single">
          <header>
            <h3>安全扫描</h3>
            <span>OSV/NVD 在线漏洞源访问</span>
          </header>
          <div class="settings-field-grid">
            <el-checkbox v-model="securityScanDraft.onlineCveEnabled" :disabled="!canSave" class="settings-check-row span-2">开启在线 CVE 查询</el-checkbox>
            <p class="span-2 settings-inline-help">
              关闭时安全扫描只执行基线和端口风险检查；开启后会访问 OSV 和 NVD 获取 CVE 详情，并缓存查询结果。
            </p>
          </div>
        </section>

        <section v-else-if="activeTab === 'watermark'" class="settings-section single">
          <header>
            <h3>水印配置</h3>
            <span>水印模板与应用范围</span>
          </header>
          <div class="watermark-form-grid">
            <div class="settings-field-grid">
              <el-checkbox v-model="watermarkDraft.enabled" :disabled="!canSave" class="settings-check-row">开启水印</el-checkbox>
              <label>
                <span>水印模板</span>
                <el-input v-model="watermarkDraft.text" :disabled="!canSave" maxlength="160" />
              </label>
            </div>

            <section class="watermark-page-picker">
              <header>
                <div>
                  <strong>应用页面</strong>
                  <span>已选择 {{ watermarkDraft.pages.length }} 个页面</span>
                </div>
                <el-button v-if="canSave" @click="toggleAllWatermarkPages">
                  {{ watermarkDraft.pages.length === allPageKeys.length ? '清空选择' : '全选页面' }}
                </el-button>
              </header>
              <div class="watermark-page-groups">
                <article v-for="group in watermarkPageGroups" :key="group.key" class="watermark-page-group">
                  <h3>{{ group.label }}</h3>
                  <template v-if="canSave">
                    <el-button
                      v-for="page in group.pages"
                      :key="page.key"
                      :class="{ active: selectedPages.has(page.key) }"
                      @click="toggleWatermarkPage(page.key)"
                    >
                      <AppIcon :name="selectedPages.has(page.key) ? 'check' : 'circleHelp'" :size="15" />
                      {{ page.label }}
                    </el-button>
                  </template>
                  <template v-else>
                    <span
                      v-for="page in group.pages"
                      :key="page.key"
                      class="watermark-readonly-page"
                      :class="{ active: selectedPages.has(page.key) }"
                    >
                      <AppIcon :name="selectedPages.has(page.key) ? 'check' : 'circleHelp'" :size="15" />
                      {{ page.label }}
                    </span>
                  </template>
                </article>
              </div>
            </section>
          </div>
        </section>

        <section v-else-if="activeTab === 'terminal'" class="settings-section single">
          <header>
            <h3>终端设置</h3>
            <span>作用于 Web SSH 终端和批量执行</span>
          </header>
          <div class="terminal-settings-groups">
            <section>
              <h4>连接握手</h4>
              <div class="settings-field-grid terminal-settings-field-grid">
                <label>
                  <span>SSH 连接超时秒数</span>
                  <el-input-number v-model="terminalSettingsDraft.sshConnectTimeoutSeconds" :disabled="!canSave" :min="1" :max="300" />
                </label>
                <label>
                  <span>SSH Banner 超时秒数</span>
                  <el-input-number v-model="terminalSettingsDraft.sshBannerTimeoutSeconds" :disabled="!canSave" :min="1" :max="300" />
                </label>
                <label>
                  <span>SSH 认证超时秒数</span>
                  <el-input-number v-model="terminalSettingsDraft.sshAuthTimeoutSeconds" :disabled="!canSave" :min="1" :max="300" />
                </label>
                <label>
                  <span>SSH 连接重试次数</span>
                  <el-input-number v-model="terminalSettingsDraft.sshConnectAttempts" :disabled="!canSave" :min="1" :max="10" />
                </label>
                <label>
                  <span>SSH 重试基础间隔 ms</span>
                  <el-input-number v-model="terminalSettingsDraft.sshRetryDelayMs" :disabled="!canSave" :min="0" :max="10000" />
                </label>
              </div>
            </section>

            <section>
              <h4>会话保活</h4>
              <div class="settings-field-grid terminal-settings-field-grid">
                <label>
                  <span>SSH Keepalive 间隔秒数</span>
                  <el-input-number v-model="terminalSettingsDraft.sshKeepaliveSeconds" :disabled="!canSave" :min="0" :max="3600" />
                </label>
                <label>
                  <span>WebSocket 心跳间隔秒数</span>
                  <el-input-number v-model="terminalSettingsDraft.webSocketHeartbeatSeconds" :disabled="!canSave" :min="0" :max="3600" />
                </label>
                <label>
                  <span>闲置断开分钟数</span>
                  <el-input-number v-model="terminalSettingsDraft.idleDisconnectMinutes" :disabled="!canSave" :min="0" :max="1440" />
                </label>
              </div>
            </section>

            <section>
              <h4>读取与命令</h4>
              <div class="settings-field-grid terminal-settings-field-grid">
                <label>
                  <span>初始读取超时秒数</span>
                  <el-input-number v-model="terminalSettingsDraft.initialReadTimeoutSeconds" :disabled="!canSave" :min="1" :max="60" />
                </label>
                <label>
                  <span>初始读取空闲 ms</span>
                  <el-input-number v-model="terminalSettingsDraft.initialReadIdleTimeoutMs" :disabled="!canSave" :min="50" :max="10000" />
                </label>
                <label>
                  <span>命令读取超时秒数</span>
                  <el-input-number v-model="terminalSettingsDraft.commandReadTimeoutSeconds" :disabled="!canSave" :min="1" :max="3600" />
                </label>
                <label>
                  <span>命令读取空闲 ms</span>
                  <el-input-number v-model="terminalSettingsDraft.commandReadIdleTimeoutMs" :disabled="!canSave" :min="50" :max="10000" />
                </label>
                <label>
                  <span>输出轮询间隔 ms</span>
                  <el-input-number v-model="terminalSettingsDraft.readerPollIntervalMs" :disabled="!canSave" :min="10" :max="1000" />
                </label>
              </div>
            </section>

            <section>
              <h4>启动辅助</h4>
              <div class="settings-field-grid terminal-settings-field-grid">
                <label>
                  <span>CWD Hook 回显抑制 ms</span>
                  <el-input-number v-model="terminalSettingsDraft.cwdHookSuppressEchoMs" :disabled="!canSave" :min="0" :max="10000" />
                </label>
                <label>
                  <span>CWD Hook 排空超时 ms</span>
                  <el-input-number v-model="terminalSettingsDraft.cwdHookDrainTimeoutMs" :disabled="!canSave" :min="100" :max="10000" />
                </label>
                <label>
                  <span>CWD Hook 排空空闲 ms</span>
                  <el-input-number v-model="terminalSettingsDraft.cwdHookDrainIdleTimeoutMs" :disabled="!canSave" :min="50" :max="10000" />
                </label>
              </div>
            </section>

            <section>
              <h4>显示默认</h4>
              <div class="settings-field-grid terminal-settings-field-grid">
                <label>
                  <span>默认列数</span>
                  <el-input-number v-model="terminalSettingsDraft.defaultCols" :disabled="!canSave" :min="40" :max="300" />
                </label>
                <label>
                  <span>默认行数</span>
                  <el-input-number v-model="terminalSettingsDraft.defaultRows" :disabled="!canSave" :min="10" :max="120" />
                </label>
                <label>
                  <span>默认字号</span>
                  <el-input-number v-model="terminalSettingsDraft.defaultFontSize" :disabled="!canSave" :min="10" :max="24" />
                </label>
                <label>
                  <span>滚屏行数</span>
                  <el-input-number v-model="terminalSettingsDraft.scrollbackLines" :disabled="!canSave" :min="100" :max="50000" />
                </label>
              </div>
            </section>

            <section>
              <h4>批量执行</h4>
              <div class="settings-field-grid terminal-settings-field-grid">
                <label>
                  <span>最大主机数</span>
                  <el-input-number v-model="terminalSettingsDraft.bulkExecutionMaxTargets" :disabled="!canSave" :min="1" :max="1000" />
                </label>
              </div>
            </section>
          </div>
        </section>
      </article>

      <article class="settings-preview-panel">
        <header>
          <h2>{{ currentTab.title }}</h2>
          <span>{{ currentTab.label }}</span>
        </header>
        <div class="settings-preview-body">
          <template v-if="activeTab === 'system'">
            <section class="settings-preview-brand">
              <img :src="siteIdentityDraft.iconUrl" :alt="siteIdentityDraft.appName" />
              <div>
                <strong>{{ siteIdentityDraft.appName }}</strong>
                <span>{{ siteIdentityDraft.appSubtitle }}</span>
              </div>
            </section>
            <section class="settings-preview-meta">
              <span>浏览器标题</span>
              <strong>{{ siteIdentityDraft.browserTitle }}</strong>
              <span>2FA 发行方</span>
              <strong>{{ siteIdentityDraft.totpIssuer }}</strong>
              <span>登录过期</span>
              <strong>{{ authSessionMinutesFromDisplay() }} 分钟</strong>
            </section>
            <section class="settings-preview-login">
              <span>{{ previewLoginBadge }}</span>
              <strong>{{ previewLoginTitle }}</strong>
              <p>{{ previewLoginDescription }}</p>
              <em>{{ previewLoginCopyright }}</em>
            </section>
            <section class="settings-preview-footer" :style="{ color: layoutFooterDraft.color, fontSize: `${layoutFooterDraft.fontSize}px` }">
              <span>{{ previewFooterText }}</span>
              <a v-if="layoutFooterDraft.linkText && layoutFooterDraft.linkUrl">{{ previewFooterLink }}</a>
            </section>
          </template>

          <template v-else-if="activeTab === 'dashboard'">
            <section class="settings-preview-hero">
              <span>{{ previewHeroBadge }}</span>
              <img class="settings-preview-typing-svg" :src="previewHeroSvgUrl" :alt="previewHeroLines.join(' / ')" />
              <p>{{ previewDescription }}</p>
            </section>
          </template>

          <template v-else-if="activeTab === 'logRetention'">
            <section class="settings-preview-meta">
              <span>RDP 录像</span>
              <strong>{{ logRetentionDraft.rdpRecordingEnabled ? '录像开启' : '录像关闭' }}</strong>
              <span>登录 / 操作日志</span>
              <strong>{{ logRetentionDraft.loginLogsDays }} / {{ logRetentionDraft.operationLogsDays }} 天</strong>
              <span>终端命令 / 文件审计</span>
              <strong>{{ logRetentionDraft.terminalCommandAuditDays }} / {{ logRetentionDraft.terminalFileAuditDays }} 天</strong>
              <span>终端会话 / RDP 录像</span>
              <strong>{{ logRetentionDraft.terminalSessionDays }} / {{ logRetentionDraft.rdpRecordingDays }} 天</strong>
            </section>
          </template>

          <template v-else-if="activeTab === 'securityScan'">
            <section class="settings-preview-meta">
              <span>CVE 查询</span>
              <strong>{{ securityScanDraft.onlineCveEnabled ? '在线开启' : '默认关闭' }}</strong>
              <span>漏洞源</span>
              <strong>{{ securityScanDraft.onlineCveEnabled ? 'OSV / NVD' : '不访问外网' }}</strong>
            </section>
          </template>

          <template v-else-if="activeTab === 'watermark'">
            <section class="watermark-preview-box">
              <div class="watermark-preview-content">
                <strong>{{ siteIdentityDraft.appShortName }}</strong>
                <span>系统页面</span>
                <p>{{ watermarkPreviewText }}</p>
              </div>
              <WatermarkOverlay v-if="watermarkDraft.enabled" :text="watermarkPreviewText" />
            </section>
          </template>

          <template v-else-if="activeTab === 'terminal'">
            <section class="settings-preview-meta">
              <span>SSH 连接 / 认证超时</span>
              <strong>{{ terminalSettingsDraft.sshConnectTimeoutSeconds }} / {{ terminalSettingsDraft.sshAuthTimeoutSeconds }} 秒</strong>
              <span>Keepalive / 心跳</span>
              <strong>{{ terminalSettingsDraft.sshKeepaliveSeconds || '关闭' }} / {{ terminalSettingsDraft.webSocketHeartbeatSeconds || '关闭' }}</strong>
              <span>闲置断开</span>
              <strong>{{ terminalSettingsDraft.idleDisconnectMinutes ? `${terminalSettingsDraft.idleDisconnectMinutes} 分钟` : '不自动断开' }}</strong>
              <span>默认终端</span>
              <strong>{{ terminalSettingsDraft.defaultCols }}x{{ terminalSettingsDraft.defaultRows }} · {{ terminalSettingsDraft.defaultFontSize }}px · {{ terminalSettingsDraft.scrollbackLines }} 行</strong>
              <span>批量执行上限</span>
              <strong>{{ terminalSettingsDraft.bulkExecutionMaxTargets }} 台主机</strong>
            </section>
          </template>
        </div>
      </article>
    </template>
    <div v-else class="permission-empty">暂无可用功能</div>
  </section>
</template>
