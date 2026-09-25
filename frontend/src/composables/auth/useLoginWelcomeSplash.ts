import { onBeforeUnmount, onMounted, ref } from 'vue';

export const LOGIN_WELCOME_DISPLAY_MS = 2200;
export const LOGIN_WELCOME_FADE_MS = 400;

type TimerHandle = ReturnType<typeof setTimeout>;

/** Each login page mount owns a fresh welcome animation and its timers. */
export function useLoginWelcomeSplash() {
  const isVisible = ref(true);
  const isExiting = ref(false);
  let fadeTimer: TimerHandle | undefined;
  let removeTimer: TimerHandle | undefined;

  function start() {
    fadeTimer = setTimeout(() => {
      isExiting.value = true;
      removeTimer = setTimeout(() => {
        isVisible.value = false;
      }, LOGIN_WELCOME_FADE_MS);
    }, LOGIN_WELCOME_DISPLAY_MS);
  }

  function dispose() {
    if (fadeTimer !== undefined) clearTimeout(fadeTimer);
    if (removeTimer !== undefined) clearTimeout(removeTimer);
    fadeTimer = undefined;
    removeTimer = undefined;
  }

  onMounted(start);
  onBeforeUnmount(dispose);
  return { isVisible, isExiting };
}
