import { createRenderer, defineComponent, ref } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useLockScreen, useLockScreenStatus } from '../useLockScreen';

const renderer = createRenderer<Record<string, unknown>, Record<string, unknown>>({
  patchProp: () => {}, insert: () => {}, remove: () => {},
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  setText: () => {}, setElementText: () => {}, parentNode: () => null, nextSibling: () => null,
});
const disposers: Array<() => void> = [];
function mountComposable<Result>(setup: () => Result): Result {
  let result!: Result;
  const app = renderer.createApp(defineComponent({ setup() { result = setup(); return () => null; } }));
  app.mount({});
  disposers.push(() => app.unmount());
  return result;
}

async function flushPromises() {
  for (let index = 0; index < 10; index += 1) await Promise.resolve();
}

afterEach(() => {
  disposers.splice(0).forEach(dispose => dispose());
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('lock screen flow', () => {
  it('starts on the clock page, rejects empty passwords, and clears secrets on return', async () => {
    const unlock = vi.fn();
    const locked = ref(true);
    const screen = mountComposable(() => useLockScreen(locked, unlock, vi.fn()));
    expect(screen.showLogin.value).toBe(false);
    screen.openLogin();
    expect(screen.showLogin.value).toBe(true);
    screen.password.value = '   ';
    await screen.submit();
    expect(unlock).not.toHaveBeenCalled();
    screen.password.value = 'secret';
    screen.message.value = 'error';
    screen.back();
    expect(screen.showLogin.value).toBe(false);
    expect(screen.password.value).toBe('');
    expect(screen.message.value).toBe('');
    locked.value = false;
    screen.openLogin();
    expect(screen.showLogin.value).toBe(false);
  });

  it('keeps failed authentication locked and blocks duplicate submits and navigation while busy', async () => {
    let rejectRequest!: (error: Error) => void;
    const unlock = vi.fn(() => new Promise((_resolve, reject) => { rejectRequest = reject; }));
    const locked = ref(true);
    const screen = mountComposable(() => useLockScreen(locked, unlock, vi.fn()));
    screen.openLogin();
    screen.password.value = ' password with spaces ';
    const request = screen.submit();
    await screen.submit();
    screen.back();
    expect(screen.busy.value).toBe(true);
    expect(screen.showLogin.value).toBe(true);
    expect(unlock).toHaveBeenCalledExactlyOnceWith(' password with spaces ');
    rejectRequest(new Error('密码错误'));
    await request;
    expect(screen.message.value).toBe('密码错误');
    expect(screen.busy.value).toBe(false);
    expect(locked.value).toBe(true);
  });

  it('uses the server callback to unlock and resets the next lock cycle', async () => {
    const locked = ref(true);
    const unlock = vi.fn(async () => { locked.value = false; });
    const screen = mountComposable(() => useLockScreen(locked, unlock, vi.fn()));
    screen.openLogin();
    screen.password.value = 'secret';
    await screen.submit();
    expect(locked.value).toBe(false);
    expect(screen.password.value).toBe('');
    locked.value = true;
    expect(screen.showLogin.value).toBe(false);
    expect(screen.message.value).toBe('');
  });

  it('relogin uses logout, does not unlock locally, and reports failures', async () => {
    const locked = ref(true);
    const logout = vi.fn().mockRejectedValueOnce(new Error('logout failed')).mockResolvedValueOnce(undefined);
    const unlock = vi.fn();
    const screen = mountComposable(() => useLockScreen(locked, unlock, logout));
    screen.openLogin();
    await screen.submit(true);
    expect(screen.message.value).toBe('logout failed');
    expect(locked.value).toBe(true);
    await screen.submit(true);
    expect(logout).toHaveBeenCalledTimes(2);
    expect(unlock).not.toHaveBeenCalled();
    expect(locked.value).toBe(true);
  });
});

describe('lock screen device status', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 17, 8, 9, 59));
    const events = new EventTarget();
    vi.stubGlobal('window', {
      setInterval, clearInterval,
      addEventListener: events.addEventListener.bind(events),
      removeEventListener: events.removeEventListener.bind(events),
      dispatchEvent: events.dispatchEvent.bind(events),
    });
    vi.stubGlobal('navigator', { onLine: true });
  });

  it('updates local time and connectivity only while locked', () => {
    const locked = ref(true);
    const status = mountComposable(() => useLockScreenStatus(locked));
    expect(status.time.value).toBe('08:09');
    expect(status.date.value).toBe('10月17号，星期六');
    vi.advanceTimersByTime(1000);
    expect(status.time.value).toBe('08:10');
    Object.assign(navigator, { onLine: false });
    window.dispatchEvent(new Event('offline'));
    expect(status.online.value).toBe(false);
    locked.value = false;
    Object.assign(navigator, { onLine: true });
    window.dispatchEvent(new Event('online'));
    expect(status.online.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    locked.value = true;
    expect(status.online.value).toBe(true);
    disposers.pop()!();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('uses an honest fallback for unavailable and failing battery APIs', async () => {
    const locked = ref(true);
    const status = mountComposable(() => useLockScreenStatus(locked));
    expect(status.level.value).toBe('--%');
    expect(status.batteryStatus.value).toBe('电池信息不可用');
    Object.assign(navigator, { getBattery: vi.fn().mockRejectedValue(new Error('unsupported')) });
    locked.value = false;
    locked.value = true;
    await flushPromises();
    expect(status.level.value).toBe('--%');
    expect(status.remaining.value).toBe('');
  });

  it('tracks battery changes, finite durations, and removes all battery listeners', async () => {
    const battery = Object.assign(new EventTarget(), { charging: true, chargingTime: 3660, dischargingTime: Infinity, level: 0.42 });
    const add = vi.spyOn(battery, 'addEventListener');
    const remove = vi.spyOn(battery, 'removeEventListener');
    Object.assign(navigator, { getBattery: vi.fn().mockResolvedValue(battery) });
    const locked = ref(true);
    const status = mountComposable(() => useLockScreenStatus(locked));
    await flushPromises();
    expect(status.level.value).toBe('42%');
    expect(status.remaining.value).toBe('距离电池充满需要：1小时1分钟');
    expect(add).toHaveBeenCalledTimes(4);
    battery.level = 1;
    battery.chargingTime = 0;
    battery.dispatchEvent(new Event('levelchange'));
    expect(status.batteryStatus.value).toBe('已充满');
    expect(status.remaining.value).toBe('');
    battery.charging = false;
    battery.dischargingTime = 7200;
    battery.dispatchEvent(new Event('chargingchange'));
    expect(status.batteryStatus.value).toBe('已断开电源');
    expect(status.remaining.value).toBe('剩余可使用时间：2小时0分钟');
    locked.value = false;
    expect(remove).toHaveBeenCalledTimes(4);
    battery.level = 0.5;
    battery.dispatchEvent(new Event('levelchange'));
    expect(status.level.value).toBe('100%');
  });

  it('ignores late battery responses after unmount', async () => {
    const battery = Object.assign(new EventTarget(), { charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1 });
    const add = vi.spyOn(battery, 'addEventListener');
    let finish!: (value: typeof battery) => void;
    Object.assign(navigator, { getBattery: () => new Promise(resolve => { finish = resolve; }) });
    mountComposable(() => useLockScreenStatus(ref(true)));
    await Promise.resolve();
    disposers.pop()!();
    finish(battery);
    await Promise.resolve(); await Promise.resolve();
    expect(add).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
