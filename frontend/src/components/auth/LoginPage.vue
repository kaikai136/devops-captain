<script setup lang="ts">
import { computed, ref, watch, type CSSProperties } from 'vue';

import { useLoginForm } from '../../composables/auth/useLoginForm';
import type { LoginPayload, LoginResult } from '../../types';
import AppIcon from '@shared/components/AppIcon.vue';
import LoginFormCard from './login/LoginFormCard.vue';
import LoginVisualPanel from './login/LoginVisualPanel.vue';

const props = defineProps<{
  login: (payload: LoginPayload) => Promise<LoginResult>;
  verifyTwoFactorLogin: (code: string) => Promise<unknown>;
  verifyTwoFactorSetupLogin: (code: string) => Promise<unknown>;
}>();

type LoginLayoutKey = 'koi' | 'dual' | 'glass' | 'slide' | 'center' | 'immersive' | 'classic';
type LoginModeKey = 'light' | 'dark';
type LoginPanelKey = 'layout' | 'color' | null;

interface LoginAppearance {
  layout: LoginLayoutKey;
  mode: LoginModeKey;
  color: string;
  customColor: string;
}

const APPEARANCE_KEY = 'ops-login-appearance';
const defaultAppearance: LoginAppearance = {
  layout: 'koi',
  mode: 'light',
  color: '#2563EB',
  customColor: '#2563EB',
};

const layoutOptions: Array<{ key: LoginLayoutKey; title: string; subtitle: string }> = [
  { key: 'koi', title: 'Koi UI', subtitle: '清透分屏 + 科技插画' },
  { key: 'dual', title: '臻享双栏', subtitle: '品牌展示 + 登录表单' },
  { key: 'glass', title: '动感玻璃', subtitle: '光斑动效与仪表盘装饰' },
  { key: 'slide', title: '滑动登录', subtitle: '登录 / 注册滑动切换' },
  { key: 'center', title: '气泡简约', subtitle: '气泡背景轻量卡片' },
  { key: 'immersive', title: '分屏沉浸', subtitle: '大屏分栏沉浸布局' },
  { key: 'classic', title: '经典点阵', subtitle: '蓝图网格 + 终端登录面板' },
];

const colorOptions = ['#2563EB', '#1D4ED8', '#3B82F6', '#60A5FA', '#0EA5E9', '#0891B2', '#0F766E', '#14B8A6', '#475569', '#64748B', '#1E40AF', '#22C55E'];
const legacyAccentColors = new Set(['#FF6B35', '#EF4444', '#8B5CF6', '#EC4899']);

const {
  account,
  password,
  remember,
  sliderToken,
  sliderResetKey,
  isSubmitting,
  isVerifyingTwoFactor,
  errorMessage,
  twoFactorCode,
  twoFactorChallenge,
  twoFactorSetupChallenge,
  canSubmit,
  canSubmitTwoFactor,
  submitLogin,
  submitTwoFactor,
  submitTwoFactorSetup,
  cancelTwoFactor,
} = useLoginForm(props.login, props.verifyTwoFactorLogin, props.verifyTwoFactorSetupLogin);

const appearance = ref<LoginAppearance>(readStoredAppearance());
const activePanel = ref<LoginPanelKey>(null);

const activeColor = computed(() => (appearance.value.color === 'custom' ? normalizeHex(appearance.value.customColor) : appearance.value.color));
const effectiveDark = computed(() => appearance.value.mode === 'dark');
const modeButtonIcon = computed(() => (effectiveDark.value ? 'sun' : 'moon'));
const modeButtonLabel = computed(() => (effectiveDark.value ? '切换明亮模式' : '切换暗黑模式'));
const shellStyle = computed<CSSProperties>(() => {
  const rgb = hexToRgb(activeColor.value);
  return {
    '--login-accent': activeColor.value,
    '--login-accent-rgb': rgb,
  } as CSSProperties;
});

function readStoredAppearance(): LoginAppearance {
  if (typeof window === 'undefined') return { ...defaultAppearance };
  try {
    const stored = window.localStorage.getItem(APPEARANCE_KEY);
    if (!stored) return { ...defaultAppearance };
    return normalizeAppearance(JSON.parse(stored));
  } catch {
    return { ...defaultAppearance };
  }
}

function normalizeAppearance(value: unknown): LoginAppearance {
  const layoutKeys = new Set(layoutOptions.map((item) => item.key));
  const raw = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
  const legacyLayout = raw.layout === 'duo' ? 'dual' : raw.layout === 'bubble' ? 'center' : raw.layout === 'split' ? 'immersive' : raw.layout;
  const color = typeof raw.color === 'string' ? raw.color : '';
  const normalizedColor = color === 'custom' ? 'custom' : color.toUpperCase();
  const customColor = typeof raw.customColor === 'string' ? raw.customColor : defaultAppearance.customColor;
  const normalizedCustomColor = normalizeHex(customColor);
  const mode = typeof raw.mode === 'string' ? raw.mode : '';
  const customColorWasLegacy = legacyAccentColors.has(normalizedCustomColor);
  return {
    layout: typeof legacyLayout === 'string' && layoutKeys.has(legacyLayout as LoginLayoutKey) ? (legacyLayout as LoginLayoutKey) : defaultAppearance.layout,
    mode: mode === 'dark' ? 'dark' : defaultAppearance.mode,
    color:
      normalizedColor === 'custom'
        ? customColorWasLegacy
          ? defaultAppearance.color
          : 'custom'
        : colorOptions.includes(normalizedColor)
          ? normalizedColor
          : defaultAppearance.color,
    customColor: customColorWasLegacy ? defaultAppearance.customColor : normalizedCustomColor,
  };
}

function normalizeHex(value: string) {
  return /^#[0-9a-fA-F]{6}$/.test(value) ? value.toUpperCase() : defaultAppearance.customColor;
}

function hexToRgb(hex: string) {
  const value = normalizeHex(hex).slice(1);
  const number = Number.parseInt(value, 16);
  return `${(number >> 16) & 255}, ${(number >> 8) & 255}, ${number & 255}`;
}

function togglePanel(panel: Exclude<LoginPanelKey, null>) {
  activePanel.value = activePanel.value === panel ? null : panel;
}

function selectColor(color: string) {
  appearance.value.color = color;
}

function updateCustomHex(eventOrValue: Event | string) {
  const value = (typeof eventOrValue === 'string' ? eventOrValue : (eventOrValue.target as HTMLInputElement).value).trim();
  if (/^#[0-9a-fA-F]{6}$/.test(value)) {
    appearance.value.customColor = value.toUpperCase();
    appearance.value.color = 'custom';
  }
}

function updateCustomColorValue(value: string | null) {
  if (!value) return;
  appearance.value.customColor = normalizeHex(value);
  appearance.value.color = 'custom';
}

function toggleMode() {
  appearance.value.mode = effectiveDark.value ? 'light' : 'dark';
  activePanel.value = null;
}

watch(
  appearance,
  (value) => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(APPEARANCE_KEY, JSON.stringify(value));
  },
  { deep: true }
);

</script>

<template>
  <main
    class="login-shell"
    :class="[`login-layout-${appearance.layout}`, { 'login-dark': effectiveDark }]"
    :style="shellStyle"
    @click="activePanel = null"
  >
    <div class="login-bg" aria-hidden="true">
      <div class="login-bg-grid"></div>
      <div class="login-bg-vignette"></div>
      <div class="login-bg-shape login-bg-shape-1"></div>
      <div class="login-bg-shape login-bg-shape-2"></div>
      <div class="login-bg-shape login-bg-shape-3"></div>
      <div class="login-bg-shape login-bg-shape-4"></div>
    </div>

    <nav class="login-toolbar" aria-label="登录页外观设置" @click.stop>
      <el-button circle :class="{ active: activePanel === 'color' }" title="主题颜色" aria-label="主题颜色" @click="togglePanel('color')">
        <AppIcon name="brush" :size="18" />
      </el-button>
      <el-button circle :class="{ active: activePanel === 'layout' }" title="登录页风格" aria-label="登录页风格" @click="togglePanel('layout')">
        <AppIcon name="dashboard" :size="18" />
      </el-button>
      <el-button circle title="语言" aria-label="语言">
        <AppIcon name="globe" :size="18" />
      </el-button>
      <el-button circle :class="{ active: effectiveDark }" :title="modeButtonLabel" :aria-label="modeButtonLabel" @click="toggleMode">
        <AppIcon :name="modeButtonIcon" :size="18" />
      </el-button>
    </nav>

    <section class="login-card-shell" @click.stop>
      <div class="login-card-border" aria-hidden="true"></div>
      <div class="login-card">
        <LoginVisualPanel />
        <LoginFormCard
          v-model:account="account"
          v-model:password="password"
          v-model:remember="remember"
          v-model:slider-token="sliderToken"
          v-model:two-factor-code="twoFactorCode"
          :slider-reset-key="sliderResetKey"
          :is-submitting="isSubmitting"
          :is-verifying-two-factor="isVerifyingTwoFactor"
          :error-message="errorMessage"
          :two-factor-challenge="twoFactorChallenge"
          :two-factor-setup-challenge="twoFactorSetupChallenge"
          :can-submit="canSubmit"
          :can-submit-two-factor="canSubmitTwoFactor"
          @submit="submitLogin"
          @submit-two-factor="submitTwoFactor"
          @submit-two-factor-setup="submitTwoFactorSetup"
          @cancel-two-factor="cancelTwoFactor"
        />
      </div>
    </section>

    <aside v-if="activePanel === 'layout'" class="login-popover login-layout-panel" @click.stop>
      <header>
        <h2>登录页风格</h2>
        <p>切换不同布局与视觉样式</p>
      </header>
      <div class="login-layout-grid">
        <el-button
          v-for="layout in layoutOptions"
          :key="layout.key"
          class="login-layout-choice"
          :class="{ active: appearance.layout === layout.key }"
          @click="appearance.layout = layout.key"
        >
          <span class="login-style-preview" :class="`login-style-preview-${layout.key}`">
            <i class="login-style-preview-brand"></i>
            <span class="login-style-preview-form"><b></b><b></b><em></em></span>
          </span>
          <strong>{{ layout.title }}</strong>
          <small>{{ layout.subtitle }}</small>
          <span v-if="appearance.layout === layout.key" class="layout-check"><AppIcon name="check" :size="14" /></span>
        </el-button>
      </div>
    </aside>

    <aside v-if="activePanel === 'color'" class="login-popover login-color-panel" @click.stop>
      <header>
        <h2>主题颜色</h2>
        <p>与主题配置项同步</p>
      </header>
      <div class="login-color-grid">
        <el-button
          v-for="color in colorOptions"
          :key="color"
          circle
          :class="{ active: appearance.color === color }"
          :style="{ backgroundColor: color }"
          :aria-label="`选择颜色 ${color}`"
          @click="selectColor(color)"
        >
          <AppIcon v-if="appearance.color === color" name="check" :size="16" />
        </el-button>
      </div>
      <div class="login-custom-color">
        <el-color-picker v-model="appearance.customColor" aria-label="自定义颜色" @change="updateCustomColorValue" />
        <div>
          <strong>自定义颜色</strong>
          <span>色盘或输入 HEX</span>
          <el-input :model-value="appearance.customColor" maxlength="7" spellcheck="false" @input="updateCustomHex" />
        </div>
      </div>
    </aside>
  </main>
</template>
