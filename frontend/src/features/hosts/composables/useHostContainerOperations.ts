import { onScopeDispose, ref, watch, type Ref } from 'vue';
import { openSimpleTerminalPopup } from '../../terminal/utils/simpleHostTerminal';
import type { ManagedHost } from '../types';
import {
  containerTerminalUrl, controlHostContainer, getHostContainerLogs,
  type ContainerAction, type HostContainer,
} from '../api/monitoring';

export const containerActionLabels: Record<ContainerAction, string> = { start: '启动', stop: '停止', restart: '重启' };

export function useHostContainerOperations(
  host: Ref<ManagedHost>, enabled: Ref<boolean>, refresh: () => Promise<void>,
  confirm: (container: HostContainer, action: ContainerAction) => Promise<unknown>,
  api = { control: controlHostContainer, logs: getHostContainerLogs, open: openSimpleTerminalPopup },
) {
  const operationBusy = ref(false);
  const operationError = ref('');
  const operationMessage = ref('');
  const logsOpen = ref(false);
  const logsLoading = ref(false);
  const logsName = ref('');
  const logs = ref('');
  const logsError = ref('');
  const logsTruncated = ref(false);
  let logController: AbortController | null = null;
  let disposed = false;

  async function control(container: HostContainer, action: ContainerAction) {
    if (!enabled.value || operationBusy.value || disposed) return;
    operationBusy.value = true;
    operationError.value = '';
    operationMessage.value = '';
    const hostId = host.value.id;
    try {
      await confirm(container, action);
      if (disposed || !enabled.value || host.value.id !== hostId) return;
      await api.control(hostId, container.id, action);
      if (!disposed && host.value.id === hostId) {
        operationMessage.value = `容器${containerActionLabels[action]}成功`;
        await refresh();
      }
    } catch (reason) {
      if (!disposed && host.value.id === hostId && reason !== 'cancel' && reason !== 'close') operationError.value = (reason as Error).message || '容器操作失败';
    } finally { operationBusy.value = false; }
  }

  async function showLogs(container: HostContainer) {
    if (!enabled.value || logsLoading.value || disposed) return;
    logsOpen.value = true;
    logsLoading.value = true;
    logsName.value = container.name;
    logs.value = '';
    logsError.value = '';
    logsTruncated.value = false;
    const controller = new AbortController();
    logController = controller;
    try {
      const result = await api.logs(host.value.id, container.id, 200, { signal: controller.signal });
      if (controller.signal.aborted) return;
      logs.value = result.logs;
      logsTruncated.value = result.truncated;
    } catch (reason) {
      if (!controller.signal.aborted) logsError.value = (reason as Error).message || '日志读取失败';
    } finally {
      if (logController === controller) { logsLoading.value = false; logController = null; }
    }
  }

  function closeLogs() { logController?.abort(); logController = null; logsLoading.value = false; }
  function enterContainer(container: HostContainer) {
    if (!enabled.value || container.state !== 'running' || disposed) return;
    operationError.value = '';
    operationMessage.value = '';
    try {
      api.open(containerTerminalUrl(host.value.id, container.id), `host-container-terminal-${host.value.id}-${container.id}`);
    } catch (reason) {
      operationError.value = (reason as Error).message || '容器终端打开失败';
    }
  }
  watch(enabled, (value) => { if (!value) { logsOpen.value = false; closeLogs(); } });
  watch(() => host.value.id, () => { logsOpen.value = false; closeLogs(); operationError.value = ''; operationMessage.value = ''; });
  onScopeDispose(() => { disposed = true; closeLogs(); });
  return { operationBusy, operationError, operationMessage, logsOpen, logsLoading, logsName, logs, logsError, logsTruncated, control, showLogs, closeLogs, enterContainer };
}
