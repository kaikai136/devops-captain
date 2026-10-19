import { computed, onScopeDispose, ref, shallowReactive, watch, type Ref } from 'vue';
import { getDockerImages, getDockerNetworks, getDockerVolumes, getHostContainers, type DockerImages, type DockerNetworks, type DockerVolumes, type HostContainers } from '../api/monitoring';

export type DockerResourceTab = 'containers' | 'images' | 'networks' | 'volumes';
type ResourceData = { containers: HostContainers | null; images: DockerImages | null; networks: DockerNetworks | null; volumes: DockerVolumes | null };
type ResourceResult = { containers: HostContainers; images: DockerImages; networks: DockerNetworks; volumes: DockerVolumes };
type ResourceApi = { [K in DockerResourceTab]: (hostId: number, options: RequestInit) => Promise<ResourceResult[K]> };
const defaultApi: ResourceApi = { containers: getHostContainers, images: getDockerImages, networks: getDockerNetworks, volumes: getDockerVolumes };
const tabs: DockerResourceTab[] = ['containers', 'images', 'networks', 'volumes'];

export function useDockerResources(hostId: Ref<number>, enabled: Ref<boolean>, api: ResourceApi = defaultApi) {
  const activeTab = ref<DockerResourceTab>('containers');
  const data = shallowReactive<ResourceData>({ containers: null, images: null, networks: null, volumes: null });
  const loading = shallowReactive<Record<DockerResourceTab, boolean>>({ containers: false, images: false, networks: false, volumes: false });
  const errors = shallowReactive<Record<DockerResourceTab, string>>({ containers: '', images: '', networks: '', volumes: '' });
  const initialized = shallowReactive<Record<DockerResourceTab, boolean>>({ containers: false, images: false, networks: false, volumes: false });
  const counts = computed(() => Object.fromEntries(tabs.map((tab) => {
    const result = data[tab];
    return [tab, result ? String('containers' in result ? result.containers.length : result.total) : '—'];
  })) as Record<DockerResourceTab, string>);
  let request: AbortController | null = null;
  let requestTab: DockerResourceTab | null = null;
  let generation = 0;
  let disposed = false;
  let initialAttempted = false;

  function cancel() {
    generation += 1;
    request?.abort();
    request = null;
    if (requestTab) loading[requestTab] = false;
    requestTab = null;
  }
  async function load(tab: DockerResourceTab, force = false, select = true) {
    if (disposed || !enabled.value) return;
    if (select) activeTab.value = tab;
    if (loading[tab] && requestTab === tab) return;
    if (requestTab && requestTab !== tab) cancel();
    if (initialized[tab] && !force) return;
    if (request) cancel();
    const controller = new AbortController();
    request = controller;
    requestTab = tab;
    const currentGeneration = ++generation;
    const currentHostId = hostId.value;
    loading[tab] = true;
    errors[tab] = '';
    const timeout = setTimeout(() => {
      if (currentGeneration !== generation) return;
      errors[tab] = 'Docker 资源读取超时';
      cancel();
    }, 25000);
    controller.signal.addEventListener('abort', () => clearTimeout(timeout), { once: true });
    try {
      const result = await api[tab](currentHostId, { signal: controller.signal });
      if (currentGeneration !== generation || controller.signal.aborted || disposed || currentHostId !== hostId.value) return;
      if (!result.available) throw new Error(result.reason || 'Docker 服务不可用');
      Object.assign(data, { [tab]: result });
      initialized[tab] = true;
    } catch (reason) {
      if (currentGeneration === generation && !disposed && enabled.value) errors[tab] = (reason as Error).message || (controller.signal.aborted ? 'Docker 资源读取超时' : 'Docker 资源读取失败');
    } finally {
      clearTimeout(timeout);
      if (currentGeneration === generation) {
        loading[tab] = false;
        request = null;
        requestTab = null;
      }
    }
  }
  function select(tab: DockerResourceTab) { void load(tab, true); }
  function refreshContainers() {
    if (requestTab === 'containers') cancel();
    return load('containers', true, false);
  }
  watch(enabled, (value) => {
    if (!value) cancel();
    else if (!initialAttempted) { initialAttempted = true; void load('containers'); }
  }, { immediate: true, flush: 'sync' });
  watch(hostId, () => {
    cancel();
    for (const tab of tabs) { data[tab] = null; initialized[tab] = false; errors[tab] = ''; }
    activeTab.value = 'containers';
    initialAttempted = enabled.value;
    if (enabled.value) void load('containers');
  }, { flush: 'sync' });
  onScopeDispose(() => { disposed = true; cancel(); });
  return { activeTab, data, loading, errors, initialized, counts, select, refreshContainers };
}
