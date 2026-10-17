import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue';
import { errorMessage } from '../utils/errors';

export function useLockScreen(locked: Ref<boolean>, unlock: (password: string) => Promise<unknown>, logout: () => Promise<void>) {
  const showLogin = ref(false);
  const password = ref('');
  const message = ref('');
  const busy = ref(false);
  let generation = 0;

  watch(locked, () => {
    generation += 1;
    showLogin.value = false;
    password.value = '';
    message.value = '';
    busy.value = false;
  }, { immediate: true, flush: 'sync' });
  onBeforeUnmount(() => { generation += 1; });

  function openLogin() {
    if (locked.value && !busy.value) showLogin.value = true;
  }
  function back() {
    if (busy.value) return;
    showLogin.value = false;
    password.value = '';
    message.value = '';
  }
  async function submit(relogin = false) {
    if (!locked.value || busy.value || (!relogin && (!showLogin.value || !password.value.trim()))) return;
    busy.value = true;
    message.value = '';
    const requestGeneration = generation;
    try {
      if (relogin) await logout();
      else await unlock(password.value);
    } catch (error) {
      if (requestGeneration === generation) message.value = errorMessage(error);
    } finally {
      if (requestGeneration === generation) busy.value = false;
    }
  }
  return { showLogin, password, message, busy, openLogin, back, submit };
}

interface BatteryState extends EventTarget {
  charging: boolean;
  chargingTime: number;
  dischargingTime: number;
  level: number;
}

export function useLockScreenStatus(locked: Ref<boolean>) {
  const now = ref(new Date());
  const online = ref(true);
  const battery = ref<{ charging: boolean; chargingTime: number; dischargingTime: number; level: number } | null>(null);
  const time = computed(() => `${String(now.value.getHours()).padStart(2, '0')}:${String(now.value.getMinutes()).padStart(2, '0')}`);
  const date = computed(() => `${now.value.getMonth() + 1}月${now.value.getDate()}号，星期${'日一二三四五六'[now.value.getDay()]}`);
  const level = computed(() => battery.value ? `${Math.round(battery.value.level * 100)}%` : '--%');
  const batteryStatus = computed(() => !battery.value ? '电池信息不可用' : battery.value.charging
    ? battery.value.level >= 1 ? '已充满' : '充电中' : '已断开电源');
  const remaining = computed(() => {
    if (!battery.value) return '';
    const seconds = battery.value.charging ? battery.value.chargingTime : battery.value.dischargingTime;
    if (!Number.isFinite(seconds) || seconds <= 0) return '';
    const duration = `${Math.floor(seconds / 3600)}小时${Math.floor(seconds / 60) % 60}分钟`;
    return `${battery.value.charging ? '距离电池充满需要' : '剩余可使用时间'}：${duration}`;
  });

  watch(locked, (active, _previous, onCleanup) => {
    if (!active) return;
    let disposed = false;
    let manager: BatteryState | undefined;
    const events = ['chargingchange', 'chargingtimechange', 'dischargingtimechange', 'levelchange'];
    const updateOnline = () => { online.value = navigator.onLine; };
    const updateBattery = () => {
      if (!manager || disposed) return;
      battery.value = {
        charging: manager.charging, chargingTime: manager.chargingTime,
        dischargingTime: manager.dischargingTime, level: manager.level,
      };
    };
    now.value = new Date();
    battery.value = null;
    updateOnline();
    const timer = window.setInterval(() => { now.value = new Date(); }, 1000);
    window.addEventListener('online', updateOnline);
    window.addEventListener('offline', updateOnline);
    onCleanup(() => {
      disposed = true;
      window.clearInterval(timer);
      window.removeEventListener('online', updateOnline);
      window.removeEventListener('offline', updateOnline);
      events.forEach(event => manager?.removeEventListener(event, updateBattery));
    });
    const browser = navigator as Navigator & { getBattery?: () => Promise<BatteryState> };
    if (browser.getBattery) {
      void Promise.resolve().then(() => browser.getBattery!()).then(result => {
        if (disposed) return;
        manager = result;
        updateBattery();
        events.forEach(event => manager?.addEventListener(event, updateBattery));
      }).catch(() => { if (!disposed) battery.value = null; });
    }
  }, { immediate: true, flush: 'sync' });

  return { time, date, online, level, batteryStatus, remaining };
}
