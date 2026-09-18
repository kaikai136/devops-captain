<script setup lang="ts">
import { computed, ref, watch } from 'vue';

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

type LoginLayoutKey = 'koi' | 'glass';
type LoginModeKey = 'light' | 'dark';

interface LoginAppearance {
  layout: LoginLayoutKey;
  mode: LoginModeKey;
}

const APPEARANCE_KEY = 'ops-login-appearance';
const defaultAppearance: LoginAppearance = { layout: 'koi', mode: 'light' };
const layoutOptions: Array<{ key: LoginLayoutKey; title: string; subtitle: string }> = [
  { key: 'koi', title: 'Koi UI', subtitle: '清透分层 + 科技插画' },
  { key: 'glass', title: '动感玻璃', subtitle: '光斑动效与仪表盘装饰' },
];

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
const effectiveDark = computed(() => appearance.value.mode === 'dark');
const modeButtonIcon = computed(() => (effectiveDark.value ? 'sun' : 'moon'));
const modeButtonLabel = computed(() => (effectiveDark.value ? '切换明亮模式' : '切换暗黑模式'));

function readStoredAppearance(): LoginAppearance {
  if (typeof window === 'undefined') return { ...defaultAppearance };
  try {
    const stored = window.localStorage.getItem(APPEARANCE_KEY);
    return stored ? normalizeAppearance(JSON.parse(stored)) : { ...defaultAppearance };
  } catch {
    return { ...defaultAppearance };
  }
}

function normalizeAppearance(value: unknown): LoginAppearance {
  const layoutKeys = new Set(layoutOptions.map((item) => item.key));
  const raw = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
  const layout = raw.layout === 'glass' || raw.layout === 'koi' ? raw.layout : defaultAppearance.layout;
  return {
    layout: layoutKeys.has(layout) ? layout : defaultAppearance.layout,
    mode: raw.mode === 'dark' ? 'dark' : defaultAppearance.mode,
  };
}

function toggleLayout() {
  appearance.value.layout = appearance.value.layout === 'koi' ? 'glass' : 'koi';
}

function toggleMode() {
  appearance.value.mode = effectiveDark.value ? 'light' : 'dark';
}

watch(effectiveDark, (dark) => document.documentElement.classList.toggle('dark', dark), { immediate: true });
watch(
  appearance,
  (value) => {
    if (typeof window !== 'undefined') window.localStorage.setItem(APPEARANCE_KEY, JSON.stringify(value));
  },
  { deep: true },
);
</script>

<template>
  <main class="login-shell" :class="[`login-layout-${appearance.layout}`, { 'login-dark': effectiveDark }]">
    <div class="login-bg" aria-hidden="true">
      <div class="login-bg-grid"></div>
      <div class="login-bg-vignette"></div>
      <div class="login-bg-shape login-bg-shape-1"></div>
      <div class="login-bg-shape login-bg-shape-2"></div>
      <div class="login-bg-shape login-bg-shape-3"></div>
      <div class="login-bg-shape login-bg-shape-4"></div>
    </div>

    <nav class="login-toolbar" aria-label="登录页外观设置">
      <el-button circle :class="{ active: appearance.layout === 'glass' }" title="切换登录页模式" aria-label="切换登录页模式" @click="toggleLayout">
        <AppIcon name="dashboard" :size="18" />
      </el-button>
      <el-button circle title="语言" aria-label="语言">
        <AppIcon name="globe" :size="18" />
      </el-button>
      <el-button circle :class="{ active: effectiveDark }" :title="modeButtonLabel" :aria-label="modeButtonLabel" @click="toggleMode">
        <AppIcon :name="modeButtonIcon" :size="18" />
      </el-button>
    </nav>

    <section class="login-card-shell">
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
  </main>
</template>
