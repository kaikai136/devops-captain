import { createRenderer, h, nextTick, ref } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLoginWelcomeSplash } from '../../../../composables/auth/useLoginWelcomeSplash';

const renderer = createRenderer<object, object>({
  createElement: () => ({}),
  createText: () => ({}),
  createComment: () => ({}),
  insert: () => {},
  remove: () => {},
  setText: () => {},
  setElementText: () => {},
  patchProp: () => {},
  parentNode: () => null,
  nextSibling: () => null,
});

const unmounts: Array<() => void> = [];

function mountLogin() {
  let splash!: ReturnType<typeof useLoginWelcomeSplash>;
  const loginStep = ref('password');
  const app = renderer.createApp({
    setup() {
      splash = useLoginWelcomeSplash();
      return () => h('div', loginStep.value);
    },
  });
  app.mount({});
  const unmount = () => {
    app.unmount();
    unmounts.splice(unmounts.indexOf(unmount), 1);
  };
  unmounts.push(unmount);
  return { splash, loginStep, unmount };
}

describe('login welcome splash timing', () => {
  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    [...unmounts].forEach((unmount) => unmount());
    vi.useRealTimers();
  });

  it('shows for 2.2 seconds and keeps the form blocked throughout the 0.4 second fade', () => {
    const { splash } = mountLogin();
    expect(splash.isVisible.value).toBe(true);
    expect(splash.isExiting.value).toBe(false);

    vi.advanceTimersByTime(2199);
    expect(splash.isVisible.value).toBe(true);
    expect(splash.isExiting.value).toBe(false);

    vi.advanceTimersByTime(1);
    expect(splash.isVisible.value).toBe(true);
    expect(splash.isExiting.value).toBe(true);

    vi.advanceTimersByTime(399);
    expect(splash.isVisible.value).toBe(true);
    vi.advanceTimersByTime(1);
    expect(splash.isVisible.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([1000, 2300])('cleans up timers when unmounted at %i ms', (elapsed) => {
    const { splash, unmount } = mountLogin();
    vi.advanceTimersByTime(elapsed);
    const wasExiting = splash.isExiting.value;
    unmount();
    expect(vi.getTimerCount()).toBe(0);

    vi.advanceTimersByTime(5000);
    expect(splash.isVisible.value).toBe(true);
    expect(splash.isExiting.value).toBe(wasExiting);
  });

  it.each([1000, 2600])('replays on a new login mount after leaving at %i ms', (elapsed) => {
    const first = mountLogin();
    vi.advanceTimersByTime(elapsed);
    first.unmount();

    const second = mountLogin();
    expect(second.splash.isVisible.value).toBe(true);
    expect(second.splash.isExiting.value).toBe(false);
    vi.advanceTimersByTime(2199);
    expect(second.splash.isExiting.value).toBe(false);
    vi.advanceTimersByTime(401);
    expect(second.splash.isVisible.value).toBe(false);
  });

  it('does not replay for login retries or two-factor changes within the same mount', async () => {
    const { splash, loginStep } = mountLogin();
    vi.advanceTimersByTime(2600);

    for (const step of ['login-error', 'slider-retry', 'two-factor', 'two-factor-setup', 'password']) {
      loginStep.value = step;
      await nextTick();
      expect(splash.isVisible.value).toBe(false);
      expect(vi.getTimerCount()).toBe(0);
    }
  });
});
