<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, toRef, watch } from 'vue';
import type { InputInstance } from 'element-plus';
import { ArrowRight, LoaderCircle, LockKeyhole, Plug, UserRound, Wifi } from '@lucide/vue';
import { useLockScreen, useLockScreenStatus } from '../composables/useLockScreen';

const props = defineProps<{
  locked: boolean;
  avatarUrl: string;
  username?: string;
  displayName: string;
  firstName?: string;
  account: string;
  unlockSession: (password: string) => Promise<unknown>;
  logout: () => Promise<void>;
}>();

const locked = toRef(props, 'locked');
const { showLogin, password, message, busy, openLogin, back, submit } = useLockScreen(locked, value => props.unlockSession(value), () => props.logout());
const { time, date, online, level, batteryStatus, remaining } = useLockScreenStatus(locked);
const overlay = ref<HTMLElement | null>(null);
const passwordInput = ref<InputInstance | null>(null);
let previousFocus: HTMLElement | null = null;

function focusCurrentPage() {
  if (showLogin.value) passwordInput.value?.focus();
  else overlay.value?.focus();
}
function keepFocus(event: FocusEvent) {
  if (props.locked && event.target instanceof Node && !overlay.value?.contains(event.target)) focusCurrentPage();
}
watch(locked, async active => {
  if (active) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.addEventListener('focusin', keepFocus);
    await nextTick();
    if (props.locked) focusCurrentPage();
  } else {
    document.removeEventListener('focusin', keepFocus);
    previousFocus?.focus();
    previousFocus = null;
  }
}, { immediate: true });
watch(showLogin, async () => { await nextTick(); if (props.locked) focusCurrentPage(); });
onBeforeUnmount(() => {
  document.removeEventListener('focusin', keepFocus);
  previousFocus?.focus();
});

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Tab') return;
  const controls = Array.from(overlay.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex="0"]') ?? []);
  if (!controls.length) { event.preventDefault(); overlay.value?.focus(); return; }
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === overlay.value)) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === overlay.value)) {
    event.preventDefault(); first.focus();
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="lock-screen-slide">
      <section
        v-if="locked" ref="overlay" class="lock-screen-overlay" :class="{ 'on-lock-login': showLogin }"
        role="dialog" aria-modal="true" aria-label="锁定屏幕" tabindex="-1"
        @keydown.stop="handleKeydown" @keyup.stop="!showLogin && openLogin()" @mousedown.stop @click.stop @contextmenu.prevent
      >
        <template v-if="!showLogin">
          <div class="lock-screen-lock-box">
            <el-button text class="lock-screen-lock-icon" title="解锁屏幕" aria-label="解锁屏幕" @click="openLogin">
              <LockKeyhole :size="34" :stroke-width="1.5" />
            </el-button>
          </div>
          <div class="lock-screen-charge" aria-label="电池状态">
            <div class="lock-screen-charge-number">{{ level }}</div>
            <div class="lock-screen-charge-contrast" aria-hidden="true">
              <div class="lock-screen-charge-circle"></div>
              <ul class="lock-screen-charge-bubbles">
                <li v-for="index in 15" :key="index" :style="{ '--bubble-size': `${15 + index % 6 * 3}px`, '--bubble-left': `${10 + index * 17 % 80}%`, '--bubble-delay': `${-index * 0.37}s`, '--bubble-duration': `${2 + index % 4 * 0.4}s` }"></li>
              </ul>
            </div>
            <div class="lock-screen-charging"><div>{{ batteryStatus }}</div><div v-if="remaining">{{ remaining }}</div></div>
          </div>
          <div class="lock-screen-local-time"><div class="time">{{ time }}</div><div class="date">{{ date }}</div></div>
          <div class="lock-screen-computer-status">
            <span :class="{ offline: !online }" :title="online ? '网络已连接' : '网络已断开'" role="img" :aria-label="online ? '网络已连接' : '网络已断开'"><Wifi :size="24" /></span>
            <span :title="batteryStatus" role="img" :aria-label="batteryStatus"><Plug :size="24" /></span>
          </div>
        </template>
        <form v-else class="lock-screen-login-box" :aria-busy="busy" @submit.prevent="submit()">
          <el-avatar :size="128" shape="square" class="lock-screen-login-avatar"><UserRound :size="90" :stroke-width="1.2" /></el-avatar>
          <div class="lock-screen-username">{{ username || account || displayName }}</div>
          <el-input ref="passwordInput" v-model="password" type="password" autofocus autocomplete="current-password" placeholder="请输入登录密码" aria-label="请输入登录密码" :disabled="busy">
            <template #suffix>
              <el-button text class="lock-screen-submit-icon" aria-label="进入系统" :disabled="busy" @click="submit()">
                <LoaderCircle v-if="busy" class="lock-screen-spinner" :size="18" /><ArrowRight v-else :size="18" />
              </el-button>
            </template>
          </el-input>
          <div v-if="message" class="lock-screen-message" role="alert">{{ message }}</div>
          <div class="lock-screen-login-actions">
            <el-button text :disabled="busy" @click="back">返回</el-button>
            <el-button text :disabled="busy" @click="submit(true)">重新登录</el-button>
            <el-button text :disabled="busy" native-type="submit">进入系统</el-button>
          </div>
        </form>
      </section>
    </Transition>
  </Teleport>
</template>
