import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import 'element-plus/dist/index.css';

import WatermarkOverlay from '@shared/components/WatermarkOverlay.vue';
import WebTerminalPage from './components/terminal/WebTerminalPage.vue';
import {
  buildTemplateVariables,
  normalizeSiteIdentity,
  renderTemplate,
  SITE_IDENTITY_SETTING_KEY,
  UI_THEME_SETTING_KEY,
} from './composables/features/useSiteSettings';
import { normalizeWatermarkConfig, watermarkAppliesToPage, WATERMARK_SETTING_KEY } from './composables/features/useWatermarkSettings';
import { getCurrentUser } from './services/auth';
import { getSystemSetting, getSystemSettingOrNull } from './services/system';
import { applyUiTheme, defaultUiTheme, normalizeUiThemeConfig } from './utils/uiTheme';
import './styles/terminal.css';
import './styles/base/element-plus-theme.css';
import './styles/base/element-plus-overrides.css';

applyUiTheme(document.documentElement, defaultUiTheme);
void mountTerminalApp();

async function mountTerminalApp() {
  try {
    const setting = await getSystemSettingOrNull(UI_THEME_SETTING_KEY);
    applyUiTheme(document.documentElement, normalizeUiThemeConfig(setting?.value));
  } catch {
    // The standalone terminal keeps the default theme when public settings are unavailable.
  }

  const app = createApp(WebTerminalPage);
  app.use(ElementPlus, { locale: zhCn });
  app.mount('#terminal-app');
  void mountTerminalWatermark();
}

async function mountTerminalWatermark() {
  try {
    const [setting, session] = await Promise.all([
      getSystemSetting(WATERMARK_SETTING_KEY),
      getCurrentUser(),
    ]);
    const siteSetting = await getSystemSettingOrNull(SITE_IDENTITY_SETTING_KEY);
    const siteIdentity = normalizeSiteIdentity(siteSetting?.value);
    const config = normalizeWatermarkConfig(setting.value);
    if (!watermarkAppliesToPage(config, 'webTerminal')) return;
    const target = document.createElement('div');
    target.id = 'terminal-watermark-app';
    document.body.appendChild(target);
    createApp(WatermarkOverlay, {
      text: renderTemplate(config.text, buildTemplateVariables({ siteIdentity, user: session.user })),
      variant: 'terminal',
    }).mount(target);
  } catch {
    // Watermark is optional for the standalone terminal entry.
  }
}
