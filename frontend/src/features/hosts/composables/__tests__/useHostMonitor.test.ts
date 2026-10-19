import { effectScope, nextTick, ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ManagedHost } from '../../types';
import type { TerminalMonitorResponse } from '../../../terminal/types';
import { formatMonitorBytes, formatUptime, systemDisk, useHostMonitor } from '../useHostMonitor';

function sample(): TerminalMonitorResponse {
  return {
    system: { hostname: 'node', arch: 'x86_64', os: 'Linux', kernel: '6', uptimeSeconds: 244800 },
    cpu: { usagePercent: 42, cores: 4, load1: 1, load5: 0.5, load15: 0.2 },
    memory: { totalBytes: 1000, usedBytes: 600, availableBytes: 400, cacheBytes: 100, usagePercent: 60 },
    network: [{ name: 'eth0', rxBytesPerSecond: 1024, txBytesPerSecond: 2048 }],
    disks: [{ filesystem: '/dev/sda', type: 'ext4', mountpoint: '/', totalBytes: 100, usedBytes: 50, availableBytes: 50, usagePercent: 50 }],
  };
}

const scopes: Array<ReturnType<typeof effectScope>> = [];
afterEach(() => {
  scopes.splice(0).forEach((scope) => scope.stop());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function setup(refreshIntervalSeconds = ref(10)) {
  vi.useFakeTimers();
  const listeners = new Map<string, () => void>();
  const document = { visibilityState: 'visible', addEventListener: vi.fn((event, listener) => listeners.set(event, listener)), removeEventListener: vi.fn((event) => listeners.delete(event)) };
  vi.stubGlobal('document', document);
  const host = ref({ id: 1, os: 'centos' } as ManagedHost);
  const enabled = ref(true);
  const api = { monitor: vi.fn().mockResolvedValue(sample()), containers: vi.fn().mockResolvedValue({ available: true, containers: [] }) };
  const scope = effectScope();
  scopes.push(scope);
  const state = scope.run(() => useHostMonitor(host, enabled, api, refreshIntervalSeconds))!;
  return { host, enabled, api, scope, state, document, listeners };
}

describe('host monitor', () => {
  it('stops only the closed host scope while other open hosts keep polling', async () => {
    const first = setup();
    const second = setup();
    await vi.advanceTimersByTimeAsync(10000);
    expect(first.api.monitor).toHaveBeenCalledTimes(2);
    expect(second.api.monitor).toHaveBeenCalledTimes(2);
    first.scope.stop();
    await vi.advanceTimersByTimeAsync(30000);
    expect(first.api.monitor).toHaveBeenCalledTimes(2);
    expect(second.api.monitor).toHaveBeenCalledTimes(5);
    second.scope.stop();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('formats bytes, root disk and uptime without fabricating missing values', () => {
    expect(formatMonitorBytes(undefined)).toBe('--');
    expect(formatMonitorBytes(1024)).toBe('1.0 KiB');
    expect(formatUptime(244800)).toBe('运行 2 天 20 小时');
    expect(systemDisk(sample())?.mountpoint).toBe('/');
    expect(systemDisk(null)).toBeNull();
  });

  it('loads immediately and polls every ten seconds with at most 90 recent points', async () => {
    const { state, api } = setup();
    await vi.advanceTimersByTimeAsync(0);
    expect(state.snapshot.value?.cpu.usagePercent).toBe(42);
    expect(state.history.value[0].rx).toBe(1024);
    await vi.advanceTimersByTimeAsync(9999);
    expect(api.monitor).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.monitor).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(10000 * 100);
    expect(state.history.value).toHaveLength(90);
    expect(vi.getTimerCount()).toBe(2);
  });

  it('uses the selected 10, 15 or 20 second interval for the next poll', async () => {
    const refreshIntervalSeconds = ref(10);
    const { state, api } = setup(refreshIntervalSeconds);
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(9999);
    expect(api.monitor).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.monitor).toHaveBeenCalledTimes(2);
    const snapshot = state.snapshot.value;
    const history = state.history.value;
    await vi.advanceTimersByTimeAsync(5000);
    refreshIntervalSeconds.value = 15;
    await nextTick();
    await vi.advanceTimersByTimeAsync(14999);
    expect(api.monitor).toHaveBeenCalledTimes(2);
    expect(state.snapshot.value).toBe(snapshot);
    expect(state.history.value).toBe(history);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.monitor).toHaveBeenCalledTimes(3);
    refreshIntervalSeconds.value = 20;
    await nextTick();
    await vi.advanceTimersByTimeAsync(19999);
    expect(api.monitor).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.monitor).toHaveBeenCalledTimes(4);
    refreshIntervalSeconds.value = 10;
    await nextTick();
    await vi.advanceTimersByTimeAsync(10000);
    expect(api.monitor).toHaveBeenCalledTimes(5);
    expect(vi.getTimerCount()).toBe(2);
  });

  it('keeps values visible during manual refresh and changes interval without overlapping requests', async () => {
    const refreshIntervalSeconds = ref(10);
    const { state, api } = setup(refreshIntervalSeconds);
    await vi.advanceTimersByTimeAsync(0);
    let resolve!: (value: TerminalMonitorResponse) => void;
    api.monitor.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const snapshot = state.snapshot.value;
    const history = state.history.value;
    const pending = state.refresh();
    expect(api.monitor).toHaveBeenCalledTimes(2);
    expect(state.snapshot.value).toBe(snapshot);
    expect(state.history.value).toBe(history);
    refreshIntervalSeconds.value = 15;
    await nextTick();
    await vi.advanceTimersByTimeAsync(15000);
    await state.refresh();
    expect(api.monitor).toHaveBeenCalledTimes(2);
    resolve({ ...sample(), cpu: { ...sample().cpu, usagePercent: 75 } });
    await pending;
    expect(state.snapshot.value?.cpu.usagePercent).toBe(75);
    expect(state.history.value).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(14999);
    expect(api.monitor).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.monitor).toHaveBeenCalledTimes(3);
  });

  it('does not restart polling when the interval changes while locked', async () => {
    const refreshIntervalSeconds = ref(10);
    const { state, api, enabled, scope } = setup(refreshIntervalSeconds);
    await vi.advanceTimersByTimeAsync(0);
    enabled.value = false;
    await nextTick();
    refreshIntervalSeconds.value = 20;
    await nextTick();
    await vi.advanceTimersByTimeAsync(40000);
    expect(api.monitor).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
    enabled.value = true;
    await nextTick();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.monitor).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(19999);
    expect(api.monitor).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.monitor).toHaveBeenCalledTimes(3);
    expect(state.history.value).toHaveLength(3);
    scope.stop();
    refreshIntervalSeconds.value = 15;
    await nextTick();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps polling while hidden, pauses while locked and stops on disposal', async () => {
    const { enabled, api, scope, state, document, listeners } = setup();
    await vi.advanceTimersByTimeAsync(0);
    document.visibilityState = 'hidden';
    listeners.get('visibilitychange')?.();
    await nextTick();
    await vi.advanceTimersByTimeAsync(20000);
    expect(api.monitor).toHaveBeenCalledTimes(3);
    document.visibilityState = 'visible';
    listeners.get('visibilitychange')?.();
    await nextTick();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.monitor).toHaveBeenCalledTimes(3);
    enabled.value = false;
    await nextTick();
    expect(state.active.value).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
    scope.stop();
    await vi.advanceTimersByTimeAsync(60000);
    expect(api.monitor).toHaveBeenCalledTimes(3);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not overlap requests or commit stale responses from another host', async () => {
    const { host, api, state } = setup();
    await vi.advanceTimersByTimeAsync(0);
    let resolve!: (value: TerminalMonitorResponse) => void;
    api.monitor.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const pending = state.refresh();
    await state.refresh();
    expect(api.monitor).toHaveBeenCalledTimes(2);
    const signal = api.monitor.mock.calls[1][1].signal;
    host.value = { ...host.value, id: 2 };
    await nextTick();
    await vi.advanceTimersByTimeAsync(0);
    expect(signal.aborted).toBe(true);
    resolve({ ...sample(), cpu: { ...sample().cpu, usagePercent: 99 } });
    await pending;
    expect(state.snapshot.value?.cpu.usagePercent).toBe(42);
    expect(state.history.value).toHaveLength(1);
    expect(api.monitor).toHaveBeenCalledTimes(3);
  });

  it('preserves last values on failures and recovers without resetting history', async () => {
    const { api, state } = setup();
    await vi.advanceTimersByTimeAsync(0);
    api.monitor.mockRejectedValueOnce(new Error('SSH failed'));
    api.containers.mockRejectedValueOnce(new Error('Docker failed'));
    await state.refresh();
    await state.refreshContainers();
    expect(state.error.value).toBe('SSH failed');
    expect(state.containerError.value).toBe('Docker failed');
    expect(state.snapshot.value).not.toBeNull();
    await state.refresh();
    expect(state.error.value).toBe('');
    expect(state.history.value).toHaveLength(2);
  });

  it('does not collect Windows metrics', async () => {
    const { host, state, api } = setup();
    await vi.advanceTimersByTimeAsync(0);
    host.value = { ...host.value, os: 'windows' };
    await nextTick();
    await vi.advanceTimersByTimeAsync(20000);
    expect(state.supported.value).toBe(false);
    expect(state.snapshot.value).toBeNull();
    expect(api.monitor).toHaveBeenCalledTimes(1);
  });

  it('keeps monitoring responsive while a slow Docker request is pending', async () => {
    const { state, api } = setup();
    await vi.advanceTimersByTimeAsync(0);
    api.containers.mockImplementationOnce(() => new Promise(() => {}));
    void state.refreshContainers();
    await vi.advanceTimersByTimeAsync(10000);
    expect(api.monitor).toHaveBeenCalledTimes(2);
    expect(state.loading.value).toBe(false);
    expect(state.containersLoading.value).toBe(true);
    expect(state.snapshot.value?.cpu.usagePercent).toBe(42);
  });

  it('refreshes containers less frequently than core host metrics', async () => {
    const { api } = setup();
    await vi.advanceTimersByTimeAsync(30000);
    expect(api.monitor).toHaveBeenCalledTimes(4);
    expect(api.containers).toHaveBeenCalledTimes(2);
  });

  it('shows timeouts without clearing the last successful snapshot', async () => {
    const { state, api } = setup();
    await vi.advanceTimersByTimeAsync(0);
    api.monitor.mockImplementationOnce((_hostId, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }));
    const pending = state.refresh();
    await vi.advanceTimersByTimeAsync(20000);
    await pending;
    expect(state.error.value).toContain('超时');
    expect(state.loading.value).toBe(false);
    expect(state.snapshot.value?.cpu.usagePercent).toBe(42);
    await vi.advanceTimersByTimeAsync(10000);
    expect(state.error.value).toBe('');
  });
});
