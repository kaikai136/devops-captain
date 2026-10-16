import { computed, ref } from 'vue';
import { ApiResponseError } from '../../../api';
import { getTerminalFileContent, updateTerminalFileContent, type TerminalFileContentResponse, type TerminalFileSaveOptions } from '../api/terminal';
import { terminalFileImageMime } from '../utils/fileTypes';
import { terminalFileHash } from '../utils/fileHash';

export type FileOpenMode = 'edit' | 'preview';
export interface TerminalFileTarget { hostId: number; nodeName: string; path: string; name: string }
export interface TerminalFileTab extends TerminalFileTarget {
  id: string;
  mode: FileOpenMode;
  kind: 'text' | 'image' | 'binary';
  content: string;
  savedContent: string;
  expectedHash: string;
  conflict: boolean;
  bom: string;
  lineEnding: string;
  contentType: string;
  imageUrl: string;
  loading: boolean;
  saving: boolean;
  dirty: boolean;
  error: string;
  saveError: string;
  byteSize: number;
  revision: number;
}
interface FileApi {
  read(hostId: number, path: string, options: RequestInit): Promise<TerminalFileContentResponse>;
  write(hostId: number, path: string, content: string, options: TerminalFileSaveOptions): Promise<{ size: number }>;
}
interface Options {
  api?: FileApi;
  confirm?: (message: string) => boolean;
  onSaved?: (target: TerminalFileTarget) => void;
  onUnauthorized?: (error: unknown) => boolean;
}

export function useTerminalFiles(options: Options = {}) {
  const api = options.api ?? { read: getTerminalFileContent, write: updateTerminalFileContent };
  const confirm = options.confirm ?? ((message: string) => window.confirm(message));
  const tabs = ref<TerminalFileTab[]>([]);
  const activeId = ref<string | null>(null);
  const activeTab = computed(() => tabs.value.find(tab => tab.id === activeId.value) ?? null);
  const hasUnsaved = computed(() => tabs.value.some(tab => tab.dirty || tab.saving));
  const requests = new Map<string, AbortController>();

  function release(tab: TerminalFileTab) {
    requests.get(tab.id)?.abort();
    requests.delete(tab.id);
    if (tab.imageUrl) URL.revokeObjectURL(tab.imageUrl);
    tab.imageUrl = '';
  }
  async function load(tab: TerminalFileTab, preserveOnFailure = false) {
    release(tab);
    const controller = new AbortController();
    requests.set(tab.id, controller);
    tab.loading = true;
    tab.error = '';
    tab.saveError = '';
    try {
      const response = await api.read(tab.hostId, tab.path, { signal: controller.signal });
      const expectedHash = response.isText ? terminalFileHash(new Uint8Array(await response.blob.arrayBuffer())) : '';
      if (requests.get(tab.id) !== controller || controller.signal.aborted) return;
      tab.byteSize = response.size;
      tab.contentType = response.contentType;
      const imageMime = terminalFileImageMime(tab.name);
      if (imageMime.startsWith('image/')) {
        tab.kind = 'image';
        tab.mode = 'preview';
        tab.imageUrl = URL.createObjectURL(response.contentType.startsWith('image/')
          ? response.blob
          : new Blob([response.blob], { type: imageMime }));
      } else if (response.contentType.startsWith('image/')) {
        tab.kind = 'image';
        tab.mode = 'preview';
        tab.imageUrl = URL.createObjectURL(response.blob);
      } else if (response.isText) {
        tab.kind = 'text';
        const source = response.content ?? '';
        tab.bom = source.startsWith('\ufeff') ? '\ufeff' : '';
        tab.lineEnding = source.match(/\r\n|\r|\n/)?.[0] ?? '\n';
        tab.content = source.slice(tab.bom.length).replace(/\r\n|\r/g, '\n');
        tab.savedContent = tab.content;
        tab.expectedHash = expectedHash;
      } else {
        tab.kind = 'binary';
        tab.mode = 'preview';
      }
      tab.dirty = false;
      tab.conflict = false;
      tab.revision += 1;
    } catch (error) {
      if (requests.get(tab.id) !== controller || controller.signal.aborted) return;
      if (!options.onUnauthorized?.(error)) {
        const message = error instanceof Error ? error.message : '读取文件失败';
        if (preserveOnFailure) tab.saveError = message;
        else tab.error = message;
      }
    } finally {
      if (requests.get(tab.id) === controller) { requests.delete(tab.id); tab.loading = false; }
    }
  }
  function open(target: TerminalFileTarget, mode: FileOpenMode) {
    const id = JSON.stringify([target.hostId, target.path]);
    let tab = tabs.value.find(item => item.id === id);
    if (!tab) {
      tabs.value.push({ ...target, id, mode, kind: 'text', content: '', savedContent: '', expectedHash: '', conflict: false, bom: '', lineEnding: '\n',
        contentType: '', imageUrl: '', loading: true, saving: false, dirty: false, error: '', saveError: '', byteSize: 0, revision: 0 });
      tab = tabs.value[tabs.value.length - 1];
      void load(tab);
    } else if (mode === 'edit' && tab.kind === 'text') {
      tab.mode = 'edit';
    } else if (!tab.dirty && tab.kind === 'text') {
      tab.mode = mode;
    }
    activeId.value = id;
    return tab;
  }
  function change(tab: TerminalFileTab, content: string) {
    tab.content = content;
    tab.dirty = content !== tab.savedContent;
  }
  async function save(tab: TerminalFileTab, force = false) {
    if (tab.loading || tab.saving || !tab.dirty || tab.mode !== 'edit' || tab.kind !== 'text') return;
    if (tab.conflict && !force) return;
    const snapshot = tab.content;
    const bytesText = tab.bom + snapshot.replace(/\n/g, tab.lineEnding);
    tab.saving = true;
    tab.saveError = '';
    try {
      const expectedHash = terminalFileHash(new TextEncoder().encode(bytesText));
      const result = await api.write(tab.hostId, tab.path, bytesText, { expectedHash: tab.expectedHash, force });
      tab.savedContent = snapshot;
      tab.expectedHash = expectedHash;
      tab.conflict = false;
      tab.dirty = tab.content !== snapshot;
      tab.byteSize = result.size;
      options.onSaved?.(tab);
    } catch (error) {
      if (error instanceof ApiResponseError && error.status === 409 &&
        (error.payload as { code?: string } | null)?.code === 'file_changed') {
        tab.conflict = true;
      } else if (!options.onUnauthorized?.(error)) tab.saveError = error instanceof Error ? error.message : '保存文件失败';
    } finally { tab.saving = false; }
  }
  function reload(tab: TerminalFileTab) {
    if (tab.saving || (tab.dirty && !confirm(`“${tab.name}”有未保存的修改，重新加载会丢失修改。继续吗？`))) return;
    return load(tab, tab.revision > 0);
  }
  function cancelConflict(tab: TerminalFileTab) {
    if (!tab.loading && !tab.saving) tab.conflict = false;
  }
  function reloadConflict(tab: TerminalFileTab) {
    if (tab.loading || tab.saving || !tab.conflict) return;
    return load(tab, true);
  }
  function close(tab: TerminalFileTab) {
    if (tab.saving || (tab.dirty && !confirm(`“${tab.name}”有未保存的修改，确定放弃修改并关闭吗？`))) return false;
    const index = tabs.value.indexOf(tab);
    release(tab);
    tabs.value = tabs.value.filter(item => item.id !== tab.id);
    if (activeId.value === tab.id) activeId.value = tabs.value[Math.min(index, tabs.value.length - 1)]?.id ?? null;
    return true;
  }
  function dispose() { for (const tab of tabs.value) release(tab); }
  return { tabs, activeId, activeTab, hasUnsaved, open, change, save, reload, close, dispose, cancelConflict, reloadConflict };
}
