import { effectScope, nextTick, ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useDockerResources } from '../useDockerResources';

const scopes: ReturnType<typeof effectScope>[] = [];
function setup() {
  vi.useFakeTimers();
  const host = ref(1);
  const enabled = ref(true);
  const api = {
    containers: vi.fn().mockResolvedValue({ available: true, containers: [] }),
    images: vi.fn().mockResolvedValue({ available: true, images: [], total: 0 }),
    networks: vi.fn().mockResolvedValue({ available: true, networks: [], total: 0 }),
    volumes: vi.fn().mockResolvedValue({ available: true, volumes: [], total: 0 }),
  };
  const scope = effectScope();
  scopes.push(scope);
  const state = scope.run(() => useDockerResources(host, enabled, api))!;
  return { host, enabled, api, scope, state };
}
afterEach(() => { scopes.splice(0).forEach((scope) => scope.stop()); vi.useRealTimers(); });

describe('Docker resources', () => {
  it('loads only containers initially and never polls', async () => {
    const { state, api } = setup();
    expect(state.counts.value.images).toBe('—');
    await vi.advanceTimersByTimeAsync(90000);
    expect(api.containers).toHaveBeenCalledTimes(1);
    expect(api.images).not.toHaveBeenCalled();
    expect(api.networks).not.toHaveBeenCalled();
    expect(api.volumes).not.toHaveBeenCalled();
    expect(state.counts.value.containers).toBe('0');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('refreshes only each clicked category, including repeated clicks', async () => {
    const { state, api } = setup();
    await nextTick();
    for (const tab of ['images', 'networks', 'volumes', 'containers'] as const) {
      const before = api[tab].mock.calls.length;
      state.select(tab);
      await nextTick();
      state.select(tab);
      await nextTick();
      expect(api[tab]).toHaveBeenCalledTimes(before + 2);
      expect(state.counts.value[tab]).toBe('0');
    }
  });

  it('deduplicates pending clicks and ignores canceled late responses', async () => {
    const { state, api } = setup();
    await nextTick();
    let resolve!: (value: unknown) => void;
    api.images.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    state.select('images');
    state.select('images');
    expect(api.images).toHaveBeenCalledTimes(1);
    const signal = api.images.mock.calls[0][1].signal;
    state.select('networks');
    expect(signal.aborted).toBe(true);
    expect(state.loading.images).toBe(false);
    resolve({ available: true, images: [], total: 7 });
    await nextTick();
    expect(state.data.images).toBeNull();
    expect(state.activeTab.value).toBe('networks');
  });

  it('keeps unknown counts on first failure and cached results on subsequent failure', async () => {
    const { state, api } = setup();
    api.images.mockRejectedValueOnce(new Error('offline'));
    state.select('images');
    await nextTick();
    expect(state.counts.value.images).toBe('—');
    expect(state.errors.images).toBe('offline');
    api.images.mockResolvedValueOnce({ available: true, images: [{ id: 'abc' }], total: 1 });
    state.select('images');
    await nextTick();
    const cached = state.data.images;
    api.images.mockResolvedValueOnce({ available: false, images: [], total: 0, reason: 'unavailable' });
    state.select('images');
    await nextTick();
    expect(state.data.images).toBe(cached);
    expect(state.counts.value.images).toBe('1');
    expect(state.errors.images).toBe('unavailable');
  });

  it('cancels on lock and close, retains selection and never refreshes on unlock', async () => {
    const { state, api, enabled, scope } = setup();
    await nextTick();
    api.volumes.mockImplementation(() => new Promise(() => {}));
    state.select('volumes');
    const signal = api.volumes.mock.calls[0][1].signal;
    enabled.value = false;
    expect(signal.aborted).toBe(true);
    enabled.value = true;
    await nextTick();
    expect(state.activeTab.value).toBe('volumes');
    expect(api.volumes).toHaveBeenCalledTimes(1);
    state.select('volumes');
    const nextSignal = api.volumes.mock.calls[1][1].signal;
    scope.stop();
    expect(nextSignal.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('refreshes only containers after an operation without stealing selected view', async () => {
    const { state, api } = setup();
    await nextTick();
    state.select('images');
    await nextTick();
    await state.refreshContainers();
    expect(state.activeTab.value).toBe('images');
    expect(api.images).toHaveBeenCalledTimes(1);
    expect(api.containers).toHaveBeenCalledTimes(2);
  });

  it('times out even if transport ignores abort and permits retry', async () => {
    const { state, api } = setup();
    api.networks.mockImplementationOnce(() => new Promise(() => {}));
    state.select('networks');
    await vi.advanceTimersByTimeAsync(25000);
    expect(state.loading.networks).toBe(false);
    expect(state.errors.networks).toContain('超时');
    state.select('networks');
    await nextTick();
    expect(state.counts.value.networks).toBe('0');
  });

  it('keeps separate caches for simultaneously open hosts', async () => {
    const first = setup();
    const second = setup();
    first.state.select('images');
    await nextTick();
    expect(second.state.activeTab.value).toBe('containers');
    expect(second.state.data.images).toBeNull();
    first.scope.stop();
    second.state.select('volumes');
    await nextTick();
    expect(second.api.volumes).toHaveBeenCalledTimes(1);
  });
});
