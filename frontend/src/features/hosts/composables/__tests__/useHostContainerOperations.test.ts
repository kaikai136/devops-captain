import { effectScope, nextTick, ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ManagedHost } from '../../types';
import type { HostContainer } from '../../api/monitoring';
import { useHostContainerOperations } from '../useHostContainerOperations';

const container = { id: 'a'.repeat(64), name: 'web', state: 'running' } as HostContainer;
const scopes: Array<ReturnType<typeof effectScope>> = [];
afterEach(() => { scopes.splice(0).forEach((scope) => scope.stop()); });

function setup() {
  const enabled = ref(true);
  const host = ref({ id: 7 } as ManagedHost);
  const confirm = vi.fn().mockResolvedValue(undefined);
  const refresh = vi.fn().mockResolvedValue(undefined);
  const api = { control: vi.fn().mockResolvedValue({ success: true }), logs: vi.fn().mockResolvedValue({ logs: '', truncated: false }), open: vi.fn<(url: string, targetName: string) => void>() };
  const scope = effectScope();
  scopes.push(scope);
  const state = scope.run(() => useHostContainerOperations(host, enabled, refresh, confirm, api))!;
  return { enabled, host, confirm, refresh, api, scope, state };
}

describe('container interactions', () => {
  it('confirms all controls, prevents duplicates and refreshes after success', async () => {
    const { state, api, confirm, refresh } = setup();
    let resolve!: () => void;
    confirm.mockImplementationOnce(() => new Promise<void>((done) => { resolve = done; }));
    const pending = state.control(container, 'restart');
    await state.control(container, 'restart');
    expect(state.operationBusy.value).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(api.control).not.toHaveBeenCalled();
    resolve();
    await pending;
    expect(api.control).toHaveBeenCalledWith(7, container.id, 'restart');
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(state.operationMessage.value).toBe('容器重启成功');
    expect(state.operationBusy.value).toBe(false);
  });

  it('cancel and close do not mutate containers; failures leave an error', async () => {
    const { state, confirm, api, refresh } = setup();
    for (const reason of ['cancel', 'close']) {
      confirm.mockRejectedValueOnce(reason);
      await state.control(container, 'stop');
      expect(state.operationError.value).toBe('');
    }
    expect(api.control).not.toHaveBeenCalled();
    api.control.mockRejectedValueOnce(new Error('permission denied'));
    await state.control(container, 'stop');
    expect(state.operationError.value).toBe('permission denied');
    expect(refresh).not.toHaveBeenCalled();
    expect(state.operationBusy.value).toBe(false);
  });

  it('loads empty logs, truncated logs and errors without affecting monitor state', async () => {
    const { state, api } = setup();
    await state.showLogs(container);
    expect(state.logsOpen.value).toBe(true);
    expect(state.logs.value).toBe('');
    expect(api.logs).toHaveBeenCalledWith(7, container.id, 200, { signal: expect.any(AbortSignal) });
    api.logs.mockResolvedValueOnce({ logs: 'partial', truncated: true });
    await state.showLogs(container);
    expect(state.logsTruncated.value).toBe(true);
    api.logs.mockRejectedValueOnce(new Error('failed'));
    await state.showLogs(container);
    expect(state.logsError.value).toBe('failed');
    expect(state.logsLoading.value).toBe(false);
  });

  it('aborts pending logs when closed or locked and does not retain stale content', async () => {
    const { state, api, enabled, scope } = setup();
    let resolve!: (result: { logs: string; truncated: boolean }) => void;
    api.logs.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const pending = state.showLogs(container);
    await state.showLogs(container);
    expect(api.logs).toHaveBeenCalledTimes(1);
    const signal = api.logs.mock.calls[0][3].signal;
    enabled.value = false;
    await nextTick();
    expect(signal.aborted).toBe(true);
    expect(state.logsOpen.value).toBe(false);
    resolve({ logs: 'late', truncated: false });
    await pending;
    expect(state.logs.value).toBe('');
    scope.stop();
  });

  it('opens a scoped container terminal only while enabled and running', () => {
    const { state, api, enabled } = setup();
    state.enterContainer(container);
    expect(api.open).toHaveBeenCalledWith(`/host-terminal.html?host=7&container=${container.id}`, `host-container-terminal-7-${container.id}`);
    state.enterContainer({ ...container, state: 'exited' });
    enabled.value = false;
    state.enterContainer(container);
    expect(api.open).toHaveBeenCalledTimes(1);
  });

  it('keeps separate popup targets per host and container', () => {
    const { state, api, host } = setup();
    state.enterContainer(container);
    const other = { ...container, id: 'b'.repeat(64) };
    state.enterContainer(other);
    host.value = { id: 8 } as ManagedHost;
    state.enterContainer(container);
    expect(api.open.mock.calls.map((call) => call[1])).toEqual([
      `host-container-terminal-7-${container.id}`,
      `host-container-terminal-7-${other.id}`,
      `host-container-terminal-8-${container.id}`,
    ]);
  });

  it('shows popup errors without navigating away or using the full terminal', () => {
    const { state, api, scope } = setup();
    api.open.mockImplementationOnce(() => { throw new Error('浏览器阻止了终端弹窗'); });
    state.enterContainer(container);
    expect(state.operationError.value).toBe('浏览器阻止了终端弹窗');
    state.enterContainer(container);
    expect(state.operationError.value).toBe('');
    scope.stop();
    state.enterContainer(container);
    expect(api.open).toHaveBeenCalledTimes(2);
  });
});
