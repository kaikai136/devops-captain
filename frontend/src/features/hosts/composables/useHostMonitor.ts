import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue';
import type { ManagedHost } from '../types';
import type { TerminalMonitorResponse } from '../../terminal/types';
import { getHostContainers, getHostMonitor, type HostContainers } from '../api/monitoring';

export interface MonitorPoint {
  time: number;
  cpu: number;
  memory: number;
  disk: number | null;
  rx: number;
  tx: number;
}

export function systemDisk(data: TerminalMonitorResponse | null) {
  return data?.disks.find((disk) => disk.mountpoint === '/') ?? data?.disks[0] ?? null;
}

export function formatMonitorBytes(bytes: number | null | undefined) {
  if (bytes == null || !Number.isFinite(bytes)) return '--';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let value = Math.max(0, bytes);
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatUptime(seconds: number | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return '--';
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor(minutes % 1440 / 60);
  return days ? `运行 ${days} 天 ${hours} 小时` : `运行 ${hours} 小时 ${minutes % 60} 分钟`;
}

export function useHostMonitor(
  host: Ref<ManagedHost>,
  enabled: Ref<boolean>,
  api = { monitor: getHostMonitor, containers: getHostContainers },
  refreshIntervalSeconds: Ref<number> = ref(10),
) {
  const snapshot = shallowRef<TerminalMonitorResponse | null>(null);
  const containers = shallowRef<HostContainers | null>(null);
  const history = shallowRef<MonitorPoint[]>([]);
  const loading = ref(false);
  const containersLoading = ref(false);
  const error = ref('');
  const containerError = ref('');
  const updatedAt = ref<number | null>(null);
  const supported = computed(() => !String(host.value.os || '').toLowerCase().includes('windows'));
  const active = computed(() => enabled.value && supported.value);
  let monitorTimer: ReturnType<typeof setTimeout> | null = null;
  let containerTimer: ReturnType<typeof setTimeout> | null = null;
  let monitorController: AbortController | null = null;
  let containerController: AbortController | null = null;
  let generation = 0;

  function stop() {
    generation += 1;
    if (monitorTimer) clearTimeout(monitorTimer);
    if (containerTimer) clearTimeout(containerTimer);
    monitorTimer = null;
    containerTimer = null;
    monitorController?.abort();
    containerController?.abort();
    monitorController = null;
    containerController = null;
    loading.value = false;
    containersLoading.value = false;
  }

  async function refresh() {
    if (!active.value || loading.value) return;
    if (monitorTimer) clearTimeout(monitorTimer);
    monitorTimer = null;
    const current = generation;
    const hostId = host.value.id;
    const controller = new AbortController();
    monitorController = controller;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 20000);
    controller.signal.addEventListener('abort', () => clearTimeout(timeout), { once: true });
    loading.value = true;
    try {
      const data = await api.monitor(hostId, { signal: controller.signal });
      if (current !== generation || controller.signal.aborted) return;
      const time = Date.now();
      snapshot.value = data;
      updatedAt.value = time;
      error.value = '';
      history.value = [...history.value.filter((point) => point.time > time - 15 * 60 * 1000), {
        time, cpu: data.cpu.usagePercent, memory: data.memory.usagePercent,
        disk: systemDisk(data)?.usagePercent ?? null,
        rx: data.network.reduce((total, item) => total + item.rxBytesPerSecond, 0),
        tx: data.network.reduce((total, item) => total + item.txBytesPerSecond, 0),
      }].slice(-90);
    } catch (reason) {
      if (current === generation) {
        if (timedOut) error.value = '监控采集超时，稍后自动重试';
        else if (!controller.signal.aborted) error.value = (reason as Error).message || '监控数据读取失败';
      }
    } finally {
      clearTimeout(timeout);
      if (current === generation) {
        loading.value = false;
        monitorController = null;
        if (active.value) monitorTimer = setTimeout(refresh, refreshIntervalSeconds.value * 1000);
      }
    }
  }

  watch(refreshIntervalSeconds, (seconds) => {
    if (monitorTimer) clearTimeout(monitorTimer);
    monitorTimer = null;
    if (active.value && !loading.value) monitorTimer = setTimeout(refresh, seconds * 1000);
  });

  async function refreshContainers() {
    if (!active.value || containersLoading.value) return;
    if (containerTimer) clearTimeout(containerTimer);
    containerTimer = null;
    const current = generation;
    const hostId = host.value.id;
    const controller = new AbortController();
    containerController = controller;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 25000);
    controller.signal.addEventListener('abort', () => clearTimeout(timeout), { once: true });
    containersLoading.value = true;
    try {
      const data = await api.containers(hostId, { signal: controller.signal });
      if (current !== generation || controller.signal.aborted) return;
      containers.value = data;
      containerError.value = '';
    } catch (reason) {
      if (current === generation) {
        if (timedOut) containerError.value = '容器采集超时，主机监控不受影响';
        else if (!controller.signal.aborted) containerError.value = (reason as Error).message || '容器服务不可用';
      }
    } finally {
      clearTimeout(timeout);
      if (current === generation) {
        containersLoading.value = false;
        containerController = null;
        if (active.value) containerTimer = setTimeout(refreshContainers, 30000);
      }
    }
  }

  watch([() => host.value.id, () => host.value.os, active], ([hostId, os], previous) => {
    stop();
    if (!previous || hostId !== previous[0] || os !== previous[1]) {
      snapshot.value = null;
      containers.value = null;
      history.value = [];
      error.value = '';
      containerError.value = '';
      updatedAt.value = null;
    }
    if (active.value) { void refresh(); void refreshContainers(); }
  }, { immediate: true });
  onScopeDispose(() => {
    stop();
  });
  async function reload() {
    stop();
    await Promise.all([refresh(), refreshContainers()]);
  }
  return { snapshot, containers, history, loading, containersLoading, error, containerError, updatedAt, supported, active, refresh, refreshContainers, reload };
}
