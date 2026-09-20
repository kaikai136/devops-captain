import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue';

import { ApiUnauthorizedError } from '../../../api';
import {
  buildTerminalFileDownloadRawUrl,
  createTerminalFileEntry,
  deleteTerminalFileEntry,
  getTerminalFileProperties,
  listTerminalDownloadFiles,
  listTerminalFiles,
  renameTerminalFileEntry,
  updateTerminalFileProperties,
  uploadTerminalFile,
} from '../api/terminal';
import type { TerminalDownloadProtocol, TerminalFileEntry, TerminalFileListResponse, TerminalFileProperties } from '../types';
import { joinTerminalPath, parentTerminalDirectoryPath } from '../utils/paths';
import { formatTerminalFileSizeValue } from '../utils/protocol';

export type SftpTransferKind = 'upload' | 'download';
export type SftpTransferStatus = 'queued' | 'running' | 'success' | 'error' | 'canceled';
export type SftpFileCreateMode = 'file' | 'directory' | 'symlink';

export interface SftpSession { key: string; hostId: number; currentCwd: string }
export interface SftpFileUploadItem { file: File; relativePath?: string }
export interface SftpTransferRecord {
  id: string; kind: SftpTransferKind; status: SftpTransferStatus; name: string; path: string; currentFile: string;
  currentBytes: number; currentTotalBytes: number; completedFiles: number; totalFiles: number; progress: number; error: string;
  canceled: boolean; abortController: AbortController; createdAt: number; updatedAt: number;
}
export interface SftpRenameState { path: string; originalName: string; draftName: string; saving: boolean; error: string }
export interface SftpDeleteDialogState {
  visible: boolean; entry: TerminalFileEntry | null; entries: TerminalFileEntry[]; deleting: boolean; error: string;
}
export interface SftpCreateDialogState {
  visible: boolean; mode: SftpFileCreateMode; name: string; targetPath: string; octalMode: string;
  openAfterCreate: boolean; saving: boolean; error: string;
}
export interface SftpPropertiesDraft { owner: string; group: string; octalMode: string }
export interface SftpPropertiesDialogState {
  visible: boolean; loading: boolean; saving: boolean; error: string; entry: TerminalFileEntry | null;
  properties: TerminalFileProperties | null; draft: SftpPropertiesDraft; recursive: boolean;
}
export interface SftpLocalWritableFile { write(data: Blob | BufferSource): Promise<void>; close(): Promise<void>; abort?(): Promise<void> }
export interface SftpLocalFileHandle { createWritable(): Promise<SftpLocalWritableFile> }
export interface SftpLocalDirectoryHandle {
  getFileHandle(name: string, options?: { create?: boolean }): Promise<SftpLocalFileHandle>;
  getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<SftpLocalDirectoryHandle>;
}
export interface SftpBrowserApi {
  listFiles(hostId: number, payload: { path: string }, options?: RequestInit): Promise<TerminalFileListResponse>;
  listDownloadFiles(hostId: number, payload: { path: string }, options?: RequestInit): Promise<TerminalFileListResponse>;
  uploadFile(hostId: number, payload: { directory: string; filename: string; relativePath: string; file: File }, options?: RequestInit): Promise<{ protocol: string }>;
  createEntry(hostId: number, endpoint: string, payload: unknown): Promise<TerminalFileProperties>;
  deleteEntry(hostId: number, payload: { path: string }): Promise<{ deleted: boolean }>;
  renameEntry(hostId: number, payload: { path: string; newName: string }): Promise<TerminalFileProperties>;
  getProperties(hostId: number, path: string): Promise<TerminalFileProperties>;
  updateProperties(hostId: number, payload: unknown): Promise<TerminalFileProperties>;
  buildDownloadUrl(hostId: number, path: string, protocol: TerminalDownloadProtocol): string;
}
export interface UseSftpBrowserOptions {
  session: MaybeRefOrGetter<SftpSession | null>; api?: SftpBrowserApi; onUnauthorized?: (error: unknown) => boolean;
  confirm?: (message: string) => boolean; fetcher?: typeof fetch;
  pickDownloadDirectory?: () => Promise<SftpLocalDirectoryHandle | null>;
}

interface DirectoryCacheEntry {
  cachedAt: number;
  response: TerminalFileListResponse;
}

const DIRECTORY_CACHE_TTL_MS = 5_000;
const DIRECTORY_CACHE_MAX_ENTRIES = 24;
const DEFAULT_DOWNLOAD_CONCURRENCY = 1;
const LOCAL_FILENAME_RESERVED_CHARS = /[<>:"/\\|?*\x00-\x1f]/g;
const LOCAL_FILENAME_RESERVED_NAMES = new Set([
  'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
  'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
]);
const defaultApi: SftpBrowserApi = {
  listFiles: listTerminalFiles, listDownloadFiles: listTerminalDownloadFiles, uploadFile: uploadTerminalFile,
  createEntry: createTerminalFileEntry, deleteEntry: deleteTerminalFileEntry, renameEntry: renameTerminalFileEntry,
  getProperties: getTerminalFileProperties, updateProperties: updateTerminalFileProperties, buildDownloadUrl: buildTerminalFileDownloadRawUrl,
};
const emptyDeleteDialog = (): SftpDeleteDialogState => ({ visible: false, entry: null, entries: [], deleting: false, error: '' });
const emptyCreateDialog = (): SftpCreateDialogState => ({
  visible: false, mode: 'file', name: '', targetPath: '', octalMode: '0644', openAfterCreate: false, saving: false, error: '',
});
const emptyPropertiesDialog = (): SftpPropertiesDialogState => ({
  visible: false, loading: false, saving: false, error: '', entry: null, properties: null,
  draft: { owner: '', group: '', octalMode: '0000' }, recursive: false,
});

export function useSftpBrowser(options: UseSftpBrowserOptions) {
  const api = options.api ?? defaultApi;
  const confirmAction = options.confirm ?? ((message: string) => window.confirm(message));
  const fetcher = options.fetcher ?? fetch;
  const entries = ref<TerminalFileEntry[]>([]);
  const selectedEntry = ref<TerminalFileEntry | null>(null);
  const selectedPaths = ref<Set<string>>(new Set());
  const selectionAnchorPath = ref('');
  const path = ref('.');
  const listProtocol = ref('');
  const error = ref('');
  const followingCwd = ref(false);
  const isLoading = ref(false);
  const rename = ref<SftpRenameState | null>(null);
  const deleteDialog = ref<SftpDeleteDialogState>(emptyDeleteDialog());
  const createDialog = ref<SftpCreateDialogState>(emptyCreateDialog());
  const propertiesDialog = ref<SftpPropertiesDialogState>(emptyPropertiesDialog());
  const transferRecords = ref<SftpTransferRecord[]>([]);
  const downloadProtocol = ref<TerminalDownloadProtocol>('auto');
  const isDragOver = ref(false);
  let listRequestId = 0;
  const directoryCache = new Map<string, DirectoryCacheEntry>();
  let activeListRequest: { key: string; controller: AbortController; promise: Promise<void> } | null = null;

  const selectedEntries = computed(() => entries.value.filter((entry) => selectedPaths.value.has(entry.path) && !isParentEntry(entry)));
  const selectedCount = computed(() => selectedEntries.value.length);
  const canDownloadSelection = computed(() => selectedEntries.value.length > 0);
  const selectionStatusText = computed(() => selectedCount.value > 1
    ? `已选 ${selectedCount.value} 项 / 共 ${entries.value.length} 项`
    : `共 ${entries.value.length} 项`);
  const protocolLabel = computed(() => formatProtocol(listProtocol.value));
  const status = computed<'idle' | 'loading' | 'success' | 'error'>(() => isLoading.value ? 'loading' : error.value ? 'error' : listProtocol.value ? 'success' : 'idle');
  const statusText = computed(() => status.value === 'loading' ? '读取中' : status.value === 'error' ? '读取失败' : status.value === 'success' ? protocolLabel.value : '待加载');
  const followCwdLabel = computed(() => followingCwd.value ? '停止跟踪终端目录' : '跟踪终端目录');
  const hasRunningTransfers = computed(() => transferRecords.value.some(isTransferActive));
  const hasClearableTransfers = computed(() => transferRecords.value.some((record) => !isTransferActive(record)));

  const currentSession = () => toValue(options.session);
  function handleError(value: unknown, fallback: string) {
    if (options.onUnauthorized?.(value)) return '';
    return value instanceof Error ? value.message : fallback;
  }
  async function loadDirectory(target = path.value, requestOptions: { force?: boolean } = {}) {
    const session = currentSession();
    if (!session) return;
    const resolvedPath = resolveDirectoryPath(target);
    const cacheKey = directoryCacheKey(session, resolvedPath);
    const cached = directoryCache.get(cacheKey);
    if (!requestOptions.force && cached && Date.now() - cached.cachedAt <= DIRECTORY_CACHE_TTL_MS) {
      cancelActiveListRequest();
      listRequestId += 1;
      applyDirectoryResponse(cached.response);
      return;
    }
    if (!requestOptions.force && activeListRequest?.key === cacheKey) return activeListRequest.promise;

    cancelActiveListRequest();
    const requestId = ++listRequestId;
    const controller = new AbortController();
    isLoading.value = true;
    error.value = '';

    const promise = (async () => {
      try {
        const response = await api.listFiles(session.hostId, { path: resolvedPath }, { signal: controller.signal });
        if (requestId !== listRequestId) return;
        cacheDirectoryResponse(session, cacheKey, response);
        applyDirectoryResponse(response);
      } catch (caught) {
        if (requestId !== listRequestId || isAbortError(caught)) return;
        error.value = handleError(caught, '目录加载失败');
      } finally {
        if (requestId === listRequestId) isLoading.value = false;
        if (activeListRequest?.controller === controller) activeListRequest = null;
      }
    })();

    activeListRequest = { key: cacheKey, controller, promise };
    return promise;
  }
  function applyDirectoryResponse(response: TerminalFileListResponse) {
    path.value = response.path;
    entries.value = sortEntries(response.entries);
    listProtocol.value = response.protocol;
    syncSelectionAfterEntriesChange();
  }
  function cacheDirectoryResponse(session: SftpSession, requestKey: string, response: TerminalFileListResponse) {
    const cached: DirectoryCacheEntry = { cachedAt: Date.now(), response };
    directoryCache.delete(requestKey);
    directoryCache.set(requestKey, cached);
    const canonicalKey = directoryCacheKey(session, response.path);
    if (canonicalKey !== requestKey) {
      directoryCache.delete(canonicalKey);
      directoryCache.set(canonicalKey, cached);
    }
    while (directoryCache.size > DIRECTORY_CACHE_MAX_ENTRIES) {
      const oldestKey = directoryCache.keys().next().value as string | undefined;
      if (!oldestKey) break;
      directoryCache.delete(oldestKey);
    }
  }
  function directoryCacheKey(session: SftpSession, target: string) {
    return `${session.key}:${session.hostId}:${target}`;
  }
  function cancelActiveListRequest() {
    activeListRequest?.controller.abort();
    activeListRequest = null;
  }
  function invalidateDirectoryCache(target = path.value) {
    const session = currentSession();
    if (!session) return;
    directoryCache.delete(directoryCacheKey(session, resolveDirectoryPath(target)));
    directoryCache.delete(directoryCacheKey(session, target));
  }
  function reset(nextPath = '.') {
    cancelActiveListRequest();
    listRequestId += 1; path.value = nextPath; entries.value = []; listProtocol.value = ''; error.value = ''; isLoading.value = false;
    setSelection([], ''); rename.value = null; deleteDialog.value = emptyDeleteDialog(); createDialog.value = emptyCreateDialog();
    propertiesDialog.value = emptyPropertiesDialog(); isDragOver.value = false;
  }
  function resolveDirectoryPath(target: string) {
    const value = String(target || '.').trim();
    if (value === '..') return parentTerminalDirectoryPath(path.value);
    return joinTerminalPath(path.value, value);
  }
  function openDirectory(entry: TerminalFileEntry) { if (currentSession() && entry.type === 'directory') void loadDirectory(entry.path) }
  function openParentDirectory() { void loadDirectory(parentTerminalDirectoryPath(path.value)) }
  function toggleFollowCwd() {
    followingCwd.value = !followingCwd.value;
    const cwd = currentSession()?.currentCwd;
    if (followingCwd.value && cwd) void loadDirectory(cwd);
  }
  function syncFollowedCwd(cwd: string) { if (followingCwd.value && cwd) void loadDirectory(cwd) }
  function select(entry: TerminalFileEntry, shiftKey = false) {
    if (!currentSession()) return;
    if (shiftKey && selectionAnchorPath.value) return selectRange(selectionAnchorPath.value, entry);
    setSelection([entry], isParentEntry(entry) ? '' : entry.path);
  }
  function setSelection(nextEntries: TerminalFileEntry[], anchorPath = nextEntries[0]?.path ?? '') {
    const selectable = nextEntries.filter((entry) => !isParentEntry(entry));
    selectedPaths.value = new Set(selectable.map((entry) => entry.path));
    selectedEntry.value = selectable[selectable.length - 1] ?? nextEntries[nextEntries.length - 1] ?? null;
    selectionAnchorPath.value = anchorPath && !isParentEntry(nextEntries.find((entry) => entry.path === anchorPath)) ? anchorPath : selectable[0]?.path ?? '';
  }
  function selectRange(anchorPath: string, entry: TerminalFileEntry) {
    const anchorIndex = entries.value.findIndex((item) => item.path === anchorPath);
    const targetIndex = entries.value.findIndex((item) => item.path === entry.path);
    if (anchorIndex === -1 || targetIndex === -1) return setSelection([entry], isParentEntry(entry) ? '' : entry.path);
    const rangeEntries = entries.value.slice(Math.min(anchorIndex, targetIndex), Math.max(anchorIndex, targetIndex) + 1).filter((item) => !isParentEntry(item));
    setSelection(rangeEntries, anchorPath);
    selectedEntry.value = isParentEntry(entry) ? rangeEntries[rangeEntries.length - 1] ?? null : entry;
  }
  function syncSelectionAfterEntriesChange(preferredEntry?: TerminalFileEntry | null) {
    const availablePaths = new Set(entries.value.map((entry) => entry.path));
    const nextPaths = new Set(Array.from(selectedPaths.value).filter((itemPath) => availablePaths.has(itemPath)));
    if (preferredEntry && !isParentEntry(preferredEntry) && availablePaths.has(preferredEntry.path)) nextPaths.add(preferredEntry.path);
    selectedPaths.value = nextPaths;
    selectedEntry.value = (preferredEntry && availablePaths.has(preferredEntry.path) ? preferredEntry : null)
      ?? entries.value.find((entry) => nextPaths.has(entry.path)) ?? defaultSelectedEntry(entries.value);
    if (selectedEntry.value && !isParentEntry(selectedEntry.value)) {
      selectionAnchorPath.value = selectedEntry.value.path;
      if (!selectedPaths.value.has(selectedEntry.value.path)) selectedPaths.value = new Set([selectedEntry.value.path]);
    } else selectionAnchorPath.value = '';
  }
  const isSelected = (entry: TerminalFileEntry) => selectedPaths.value.has(entry.path);
  function actionEntries(entry: TerminalFileEntry | null | undefined = selectedEntry.value) {
    if (entry && !isParentEntry(entry) && selectedPaths.value.has(entry.path)) return selectedEntries.value;
    if (entry && !isParentEntry(entry)) return [entry];
    return selectedEntries.value;
  }

  function startRename(entry: TerminalFileEntry) {
    if (!currentSession() || isParentEntry(entry)) return;
    setSelection([entry], entry.path);
    rename.value = { path: entry.path, originalName: entry.name, draftName: entry.name, saving: false, error: '' };
  }
  function cancelRename() { rename.value = null }
  const isRenaming = (entry: TerminalFileEntry) => rename.value?.path === entry.path;
  async function saveRename() {
    const session = currentSession();
    const state = rename.value;
    if (!session || !state || state.saving) return;
    const newName = state.draftName.trim();
    if (!newName) { rename.value = { ...state, error: '请输入新名称' }; return }
    if (newName === state.originalName) { cancelRename(); return }
    rename.value = { ...state, saving: true, error: '' };
    try {
      await api.renameEntry(session.hostId, { path: state.path, newName });
      rename.value = null;
      invalidateDirectoryCache(path.value);
      await loadDirectory(path.value, { force: true });
    } catch (caught) {
      const message = handleError(caught, '重命名失败');
      if (message) rename.value = { ...state, saving: false, error: message };
    }
  }
  function openDeleteDialog(target: TerminalFileEntry | TerminalFileEntry[] | null = actionEntries()) {
    if (!currentSession()) return;
    const targetEntries = Array.isArray(target) ? target : target ? [target] : [];
    const deletableEntries = targetEntries.filter((entry) => !isParentEntry(entry));
    if (!deletableEntries.length) return;
    setSelection(deletableEntries, deletableEntries[0].path);
    deleteDialog.value = { visible: true, entry: deletableEntries[0], entries: deletableEntries, deleting: false, error: '' };
  }
  function closeDeleteDialog() { if (!deleteDialog.value.deleting) deleteDialog.value = emptyDeleteDialog() }
  async function confirmDelete() {
    const session = currentSession();
    const dialog = deleteDialog.value;
    const targetEntries = dialog.entries.length ? dialog.entries : dialog.entry ? [dialog.entry] : [];
    if (!session || !targetEntries.length || dialog.deleting) return;
    deleteDialog.value = { ...dialog, deleting: true, error: '' };
    try {
      for (const entry of targetEntries) await api.deleteEntry(session.hostId, { path: entry.path });
      deleteDialog.value = emptyDeleteDialog();
      setSelection([], '');
      invalidateDirectoryCache(path.value);
      await loadDirectory(path.value, { force: true });
    } catch (caught) {
      const message = handleError(caught, '删除失败');
      if (message) deleteDialog.value = { ...dialog, deleting: false, error: message };
    }
  }
  function openCreateDialog(mode: SftpFileCreateMode) {
    if (!currentSession()) return;
    const isDirectory = mode === 'directory';
    createDialog.value = {
      visible: true, mode, name: mode === 'file' ? 'new-file' : isDirectory ? 'new-folder' : 'new-link', targetPath: '',
      octalMode: isDirectory ? '0755' : '0644', openAfterCreate: isDirectory, saving: false, error: '',
    };
  }
  function closeCreateDialog() { if (!createDialog.value.saving) createDialog.value = emptyCreateDialog() }
  async function saveCreateDialog() {
    const session = currentSession();
    const dialog = createDialog.value;
    if (!session || !dialog.visible || dialog.saving) return;
    const name = dialog.name.trim();
    if (!name) { createDialog.value = { ...dialog, error: '请输入名称' }; return }
    if (dialog.mode === 'symlink' && !dialog.targetPath.trim()) { createDialog.value = { ...dialog, error: '请输入目标路径' }; return }
    createDialog.value = { ...dialog, saving: true, error: '' };
    try {
      const endpoint = dialog.mode === 'file' ? 'create-file' : dialog.mode === 'directory' ? 'create-directory' : 'create-symlink';
      const payload = dialog.mode === 'file'
        ? { directory: path.value, filename: name, octalMode: normalizeOctalMode(dialog.octalMode) }
        : dialog.mode === 'directory'
          ? { directory: path.value, dirname: name, octalMode: normalizeOctalMode(dialog.octalMode) }
          : { directory: path.value, linkName: name, targetPath: dialog.targetPath.trim() };
      const created = await api.createEntry(session.hostId, endpoint, payload);
      createDialog.value = emptyCreateDialog();
      if (dialog.mode === 'directory' && dialog.openAfterCreate) {
        invalidateDirectoryCache(path.value);
        await loadDirectory(created.path);
        return;
      }
      invalidateDirectoryCache(path.value);
      await loadDirectory(path.value, { force: true });
      const createdEntry = entries.value.find((entry) => entry.path === created.path || entry.name === created.name) ?? null;
      setSelection(createdEntry ? [createdEntry] : [], createdEntry?.path ?? '');
    } catch (caught) {
      const message = handleError(caught, '创建失败');
      if (message) createDialog.value = { ...dialog, saving: false, error: message };
    }
  }
  function createTitle() { return createDialog.value.mode === 'file' ? '新建文件' : createDialog.value.mode === 'directory' ? '新建文件夹' : '新建符号链接' }
  function createNameLabel() { return createDialog.value.mode === 'directory' ? '目录：' : createDialog.value.mode === 'file' ? '文件：' : '名称：' }
  function createOpenLabel() { return createDialog.value.mode === 'directory' ? '创建后打开目录' : '创建后打开文件' }
  async function openProperties(entry: TerminalFileEntry) {
    const session = currentSession();
    if (!session || isParentEntry(entry)) return;
    setSelection([entry], entry.path);
    propertiesDialog.value = {
      visible: true, loading: true, saving: false, error: '', entry, properties: null,
      draft: { owner: '', group: '', octalMode: '0000' }, recursive: false,
    };
    try {
      const properties = mergePropertiesEntryIdentity(await api.getProperties(session.hostId, entry.path), entry);
      propertiesDialog.value = {
        ...propertiesDialog.value, loading: false, properties,
        draft: { owner: ownerLabel(properties), group: groupLabel(properties), octalMode: normalizeOctalMode(properties.octalMode) },
      };
    } catch (caught) {
      const message = handleError(caught, '属性读取失败');
      if (message) propertiesDialog.value = { ...propertiesDialog.value, loading: false, error: message };
    }
  }
  function currentDirectoryName() {
    const value = String(path.value || '.').replace(/\/+$/, '');
    if (!value || value === '.') return '.';
    if (value === '/') return '/';
    return value.split('/').filter(Boolean).pop() || value;
  }
  function openCurrentDirectoryProperties() {
    if (currentSession()) void openProperties({ name: currentDirectoryName(), type: 'directory', modifiedAt: '', path: path.value });
  }
  function closePropertiesDialog() { if (!propertiesDialog.value.saving) propertiesDialog.value = emptyPropertiesDialog() }
  async function saveProperties() {
    const session = currentSession();
    const dialog = propertiesDialog.value;
    if (!session || !dialog.properties || dialog.loading || dialog.saving) return;
    const recursive = dialog.properties.type === 'directory' && dialog.recursive;
    if (recursive && !confirmAction('确认要将所有权和权限递归应用到此目录及所有子目录/文件吗？')) return;
    propertiesDialog.value = { ...dialog, saving: true, error: '' };
    try {
      const properties = await api.updateProperties(session.hostId, {
        path: dialog.properties.path, owner: dialog.draft.owner, group: dialog.draft.group,
        octalMode: normalizeOctalMode(dialog.draft.octalMode), recursive,
      });
      propertiesDialog.value = {
        ...propertiesDialog.value, saving: false, properties,
        draft: { owner: ownerLabel(properties), group: groupLabel(properties), octalMode: normalizeOctalMode(properties.octalMode) }, recursive: false,
      };
      closePropertiesDialog();
      invalidateDirectoryCache(path.value);
      await loadDirectory(path.value, { force: true });
    } catch (caught) {
      const message = handleError(caught, '属性保存失败');
      if (message) propertiesDialog.value = { ...propertiesDialog.value, saving: false, error: message };
    }
  }

  async function uploadFiles(items: SftpFileUploadItem[]) {
    const session = currentSession();
    if (!session || !items.length) return;
    const targetDirectory = path.value;
    const sessionKey = session.key;
    try {
      error.value = '';
      for (const group of groupUploadItems(items)) {
        const record = createTransferRecord('upload', group.name, targetDirectory, group.items.length);
        await runTransfer(record, async () => {
          for (const item of group.items) {
            throwIfTransferCanceled(record);
            setTransferCurrentFile(record, item.relativePath || item.file.name);
            throwIfTransferCanceled(record);
            await api.uploadFile(session.hostId, {
              directory: targetDirectory, filename: item.file.name, relativePath: item.relativePath || '', file: item.file,
            }, transferRequestOptions(record));
            completeTransferFile(record);
          }
        });
      }
      const latestSession = currentSession();
      if (latestSession?.key === sessionKey && path.value === targetDirectory) {
        invalidateDirectoryCache(targetDirectory);
        await loadDirectory(targetDirectory, { force: true });
      }
    } catch (caught) {
      if (!isTransferCancelError(caught)) error.value = handleError(caught, '文件上传失败');
    } finally { isDragOver.value = false }
  }
  async function downloadFile(entry = selectedEntry.value) { if (entry && !isParentEntry(entry)) await downloadFiles([entry]) }
  async function downloadFiles(targetEntries = actionEntries()) {
    const session = currentSession();
    const downloadableEntries = targetEntries.filter((entry) => !isParentEntry(entry));
    if (!session || !downloadableEntries.length) return;
    try {
      error.value = '';
      const directoryHandle = await pickDownloadDirectory();
      if (!directoryHandle) return;
      const usedNames = new Set<string>();
      for (const entry of downloadableEntries) {
        const record = createTransferRecord('download', entry.name, entry.path, entry.type === 'file' ? 1 : 0);
        if (entry.type === 'directory') await runTransfer(record, () => downloadDirectory(entry, directoryHandle, usedNames, session.hostId, record));
        else await runTransfer(record, () => downloadFileToDirectory(entry, directoryHandle, usedNames, session.hostId, record));
      }
    } catch (caught) {
      if (!isDownloadAbortError(caught) && !isTransferCancelError(caught)) error.value = handleError(caught, '下载失败');
    }
  }
  async function pickDownloadDirectory() {
    if (options.pickDownloadDirectory) return options.pickDownloadDirectory();
    const picker = (window as Window & { showDirectoryPicker?: (pickerOptions?: { id?: string; mode?: 'read' | 'readwrite' }) => Promise<SftpLocalDirectoryHandle> }).showDirectoryPicker;
    if (!picker) throw new Error('当前浏览器不支持选择下载目录，请使用新版 Chrome 或 Edge，并通过 HTTPS 或 localhost 打开。');
    return picker({ id: 'terminal-download-directory', mode: 'readwrite' });
  }
  async function downloadDirectory(entry: TerminalFileEntry, directoryHandle: SftpLocalDirectoryHandle, usedNames: Set<string>, hostId: number, record?: SftpTransferRecord) {
    throwIfTransferCanceled(record);
    const directoryName = uniqueDownloadFilename(sanitizeLocalFilename(entry.name || 'download'), usedNames);
    const childHandle = await directoryHandle.getDirectoryHandle(directoryName, { create: true });
    await downloadDirectoryContents(entry.path, childHandle, hostId, record);
  }
  async function downloadDirectoryContents(directoryPath: string, directoryHandle: SftpLocalDirectoryHandle, hostId: number, record?: SftpTransferRecord) {
    throwIfTransferCanceled(record);
    const response = await api.listDownloadFiles(hostId, { path: directoryPath }, transferRequestOptions(record));
    const usedNames = new Set<string>();
    const files = response.entries.filter((entry) => entry.type === 'file' && !isParentEntry(entry));
    const directories = response.entries.filter((entry) => entry.type === 'directory' && !isParentEntry(entry));
    if (record && files.length) incrementTransferTotal(record, files.length);
    for (const child of directories) {
      throwIfTransferCanceled(record);
      await downloadDirectory(child, directoryHandle, usedNames, hostId, record);
    }
    await runTransferPool(files, DEFAULT_DOWNLOAD_CONCURRENCY, (child) => downloadFileToDirectory(child, directoryHandle, usedNames, hostId, record));
  }
  async function downloadFileToDirectory(entry: TerminalFileEntry, directoryHandle: SftpLocalDirectoryHandle, usedNames: Set<string>, hostId: number, record?: SftpTransferRecord) {
    throwIfTransferCanceled(record);
    setTransferCurrentFile(record, entry.name);
    const response = await fetcher(api.buildDownloadUrl(hostId, entry.path, downloadProtocol.value), { credentials: 'include', ...transferRequestOptions(record) });
    if (response.status === 401) throw new ApiUnauthorizedError(await readDownloadError(response));
    if (!response.ok) throw new Error(await readDownloadError(response));
    throwIfTransferCanceled(record);
    const filename = downloadFilename(entry, responseFilename(response), usedNames);
    await writeResponseToDirectory(directoryHandle, filename, response, record);
    completeTransferFile(record);
  }
  function createTransferRecord(kind: SftpTransferKind, name: string, recordPath: string, totalFiles = 0) {
    const now = Date.now();
    const record: SftpTransferRecord = {
      id: `transfer-${now}-${Math.random().toString(36).slice(2, 8)}`, kind, status: 'queued', name, path: recordPath,
      currentFile: '', currentBytes: 0, currentTotalBytes: 0, completedFiles: 0, totalFiles, progress: 0, error: '', canceled: false,
      abortController: new AbortController(), createdAt: now, updatedAt: now,
    };
    transferRecords.value = [record, ...transferRecords.value];
    return record;
  }
  async function runTransfer(record: SftpTransferRecord, work: () => Promise<void>) {
    updateTransferRecord(record, { status: 'running', error: '' });
    try {
      await work();
      if (record.canceled) { updateTransferRecord(record, { status: 'canceled', progress: record.progress }); return }
      updateTransferRecord(record, { status: 'success', progress: 100, currentFile: '' });
    } catch (caught) {
      if (isTransferCancelError(caught) || record.canceled) { updateTransferRecord(record, { status: 'canceled' }); return }
      updateTransferRecord(record, { status: 'error', error: caught instanceof Error ? caught.message : '传输失败' });
      throw caught;
    }
  }
  function updateTransferRecord(record: SftpTransferRecord, patch: Partial<SftpTransferRecord>) {
    Object.assign(record, patch, { updatedAt: Date.now() });
    transferRecords.value = [...transferRecords.value];
  }
  function incrementTransferTotal(record: SftpTransferRecord | undefined, count: number) {
    if (record && count > 0) updateTransferRecord(record, { totalFiles: record.totalFiles + count, progress: calculateTransferProgress(record.completedFiles, record.totalFiles + count) });
  }
  function setTransferCurrentFile(record: SftpTransferRecord | undefined, currentFile: string) {
    if (record) updateTransferRecord(record, { currentFile, currentBytes: 0, currentTotalBytes: 0 });
  }
  function completeTransferFile(record: SftpTransferRecord | undefined) {
    if (!record) return;
    const completedFiles = record.completedFiles + 1;
    const totalFiles = Math.max(record.totalFiles, completedFiles);
    updateTransferRecord(record, { completedFiles, totalFiles, progress: calculateTransferProgress(completedFiles, totalFiles) });
  }
  function cancelTransfer(record: SftpTransferRecord) {
    if (!isTransferActive(record)) return;
    updateTransferRecord(record, { canceled: true, status: 'canceled' });
    record.abortController.abort();
  }
  function cancelAllTransfers() { for (const record of transferRecords.value) if (isTransferActive(record)) cancelTransfer(record) }
  function clearTransferRecords() { transferRecords.value = transferRecords.value.filter(isTransferActive) }
  function closeDialogs() { closeDeleteDialog(); closeCreateDialog(); cancelRename(); closePropertiesDialog() }
  function getDownloadUrl(entry: TerminalFileEntry) {
    const resolvedSession = currentSession();
    return resolvedSession ? api.buildDownloadUrl(resolvedSession.hostId, entry.path, downloadProtocol.value) : '';
  }

  return {
    entries, selectedEntry, selectedPaths, selectionAnchorPath, path, listProtocol, error, followingCwd, isLoading, rename,
    deleteDialog, createDialog, propertiesDialog, transferRecords, downloadProtocol, isDragOver, selectedEntries, selectedCount,
    canDownloadSelection, selectionStatusText, protocolLabel, status, statusText, followCwdLabel, hasRunningTransfers,
    hasClearableTransfers, loadDirectory, reset, resolveDirectoryPath, openDirectory, openParentDirectory, toggleFollowCwd,
    syncFollowedCwd, select, setSelection, selectRange, syncSelectionAfterEntriesChange, isSelected, actionEntries, startRename,
    cancelRename, isRenaming, saveRename, openDeleteDialog, closeDeleteDialog, confirmDelete, openCreateDialog, closeCreateDialog,
    saveCreateDialog, createTitle, createNameLabel, createOpenLabel, openProperties, openCurrentDirectoryProperties,
    currentDirectoryName, closePropertiesDialog, saveProperties, uploadFiles, downloadFile, downloadFiles, createTransferRecord,
    runTransfer, cancelTransfer, cancelAllTransfers, clearTransferRecords, closeDialogs, getDownloadUrl,
  };
}

function isAbortError(value: unknown) {
  return Boolean(value && typeof value === 'object' && 'name' in value && (value as { name?: string }).name === 'AbortError');
}

export function getSftpSessionLoadPath(sessionChanged: boolean, followingCwd: boolean, currentCwd: string) {
  return sessionChanged && followingCwd && currentCwd ? currentCwd : '.';
}

export function isParentEntry(entry: TerminalFileEntry | null | undefined) { return entry?.type === 'directory' && entry.name === '..' }
export function sortEntries(entries: TerminalFileEntry[]) {
  const parentEntries = entries.filter(isParentEntry);
  const normalEntries = entries.filter((entry) => !isParentEntry(entry));
  normalEntries.sort((left, right) => {
    const rank = (entry: TerminalFileEntry) => entry.name.startsWith('.') ? 0 : entry.type === 'directory' ? 1 : 2;
    const rankDifference = rank(left) - rank(right);
    return rankDifference || left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: 'base' });
  });
  return [...parentEntries.slice(0, 1), ...normalEntries];
}
export function defaultSelectedEntry(entries: TerminalFileEntry[]) {
  return entries.find((entry) => entry.type === 'file')
    ?? entries.find((entry) => entry.type === 'directory' && !isParentEntry(entry))
    ?? null;
}
export function normalizeOctalMode(value: string) { return String(value || '').replace(/[^0-7]/g, '').slice(-4).padStart(4, '0') }
export function formatProtocol(protocol: string) {
  const normalized = String(protocol || '').trim().toLowerCase();
  if (!normalized) return '';
  if (normalized.includes('sftp')) return 'SFTP';
  if (normalized.includes('enhanced')) return 'SCP enhanced';
  if (normalized.includes('scp')) return 'SCP normal';
  return protocol;
}
export function formatEntrySize(entry: TerminalFileEntry) {
  if (entry.type === 'directory' || entry.size === undefined || entry.size === null || entry.size === '') return '-';
  return formatTerminalFileSizeValue(entry.size);
}
export function formatPropertiesSize(properties: TerminalFileProperties | null) { return properties ? formatTerminalFileSizeValue(properties.size) : '-' }
export function fileText(value?: string | number) { return value === undefined || value === null || value === '' ? '-' : String(value) }
export function propertiesTypeLabel(properties: TerminalFileProperties | null) { return !properties ? '-' : properties.type === 'directory' ? '文件夹' : '文件' }
export function ownerLabel(properties: TerminalFileProperties | null) { return properties ? properties.owner || String(properties.uid) : '-' }
export function groupLabel(properties: TerminalFileProperties | null) { return properties ? properties.group || String(properties.gid) : '-' }
export function mergePropertiesEntryIdentity(properties: TerminalFileProperties, entry: TerminalFileEntry): TerminalFileProperties {
  const owner = shouldUseEntryIdentity(properties.owner, properties.uid, entry.owner) ? String(entry.owner) : properties.owner;
  const group = shouldUseEntryIdentity(properties.group, properties.gid, entry.group) ? String(entry.group) : properties.group;
  return owner === properties.owner && group === properties.group ? properties : { ...properties, owner, group };
}
function shouldUseEntryIdentity(current: string, numericId: number, entryValue?: string) {
  const value = String(entryValue || '').trim();
  return Boolean(value && value !== '-' && value !== String(numericId) && String(current || '').trim() === String(numericId));
}
export function getEntryDirectoryPath(entry: TerminalFileEntry, currentPath: string) {
  return isParentEntry(entry) ? parentTerminalDirectoryPath(currentPath) : entry.type === 'directory' ? entry.path : parentTerminalDirectoryPath(entry.path);
}
export function getEntryResolvedPath(entry: TerminalFileEntry, currentPath: string) { return isParentEntry(entry) ? parentTerminalDirectoryPath(currentPath) : entry.path }
function groupUploadItems(items: SftpFileUploadItem[]) {
  const groups = new Map<string, SftpFileUploadItem[]>();
  for (const item of items) {
    const key = item.relativePath ? item.relativePath.replace(/\\/g, '/').split('/')[0] || item.file.name : item.file.name;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return Array.from(groups, ([name, groupItems]) => ({ name, items: groupItems }));
}
function calculateTransferProgress(completedFiles: number, totalFiles: number) {
  return totalFiles <= 0 ? 0 : Math.max(0, Math.min(100, Math.round((completedFiles / totalFiles) * 100)));
}
export function isTransferActive(record: SftpTransferRecord) { return record.status === 'queued' || record.status === 'running' }
function throwIfTransferCanceled(record?: SftpTransferRecord) {
  if (record?.canceled || record?.abortController.signal.aborted) throw new DOMException('传输已取消', 'AbortError');
}
function isTransferCancelError(value: unknown) { return value instanceof DOMException && value.name === 'AbortError' }
function transferRequestOptions(record?: SftpTransferRecord): RequestInit { return record ? { signal: record.abortController.signal } : {} }
async function runTransferPool<T>(items: T[], concurrency: number, worker: (item: T) => Promise<void>) {
  let cursor = 0;
  const workerCount = Math.min(Math.max(1, concurrency), items.length);
  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (cursor < items.length) { const item = items[cursor]; cursor += 1; await worker(item) }
  }));
}
async function writeResponseToDirectory(directoryHandle: SftpLocalDirectoryHandle, filename: string, response: Response, record?: SftpTransferRecord) {
  const fileHandle = await directoryHandle.getFileHandle(filename, { create: true });
  const writable = await fileHandle.createWritable();
  const totalBytes = Number(response.headers.get('Content-Length') || 0);
  if (record) Object.assign(record, { currentBytes: 0, currentTotalBytes: Number.isFinite(totalBytes) && totalBytes > 0 ? totalBytes : 0 });
  try {
    if (!response.body) {
      const blob = await response.blob(); throwIfTransferCanceled(record); await writable.write(blob);
      if (record) record.currentBytes = blob.size;
      await writable.close(); return;
    }
    const reader = response.body.getReader();
    let writtenBytes = 0;
    while (true) {
      throwIfTransferCanceled(record);
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      await writable.write(value); writtenBytes += value.byteLength;
      if (record) record.currentBytes = writtenBytes;
    }
    throwIfTransferCanceled(record); await writable.close();
  } catch (caught) { await writable.abort?.(); throw caught }
}
async function readDownloadError(response: Response) {
  const text = await response.text();
  if (!text) return '下载失败';
  try { const payload = JSON.parse(text) as { error?: unknown }; return typeof payload.error === 'string' && payload.error ? payload.error : '下载失败' }
  catch { return text }
}
function responseFilename(response: Response) {
  const disposition = response.headers.get('Content-Disposition') || '';
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) { try { return decodeURIComponent(encoded) } catch { return encoded } }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] || '';
}
function downloadFilename(entry: TerminalFileEntry, headerFilename: string, usedNames: Set<string>) {
  return uniqueDownloadFilename(sanitizeLocalFilename(headerFilename || entry.name || 'download'), usedNames);
}
function sanitizeLocalFilename(filename: string) {
  const replaced = String(filename || 'download').replace(LOCAL_FILENAME_RESERVED_CHARS, '_').replace(/[. ]+$/g, '').trim();
  const safeName = replaced || 'download';
  return LOCAL_FILENAME_RESERVED_NAMES.has(safeName.toUpperCase()) ? `${safeName}_` : safeName;
}
function uniqueDownloadFilename(filename: string, usedNames: Set<string>) {
  if (!usedNames.has(filename.toLowerCase())) { usedNames.add(filename.toLowerCase()); return filename }
  const extensionIndex = filename.lastIndexOf('.');
  const hasExtension = extensionIndex > 0;
  const baseName = hasExtension ? filename.slice(0, extensionIndex) : filename;
  const extension = hasExtension ? filename.slice(extensionIndex) : '';
  let index = 2;
  let nextName = `${baseName} (${index})${extension}`;
  while (usedNames.has(nextName.toLowerCase())) { index += 1; nextName = `${baseName} (${index})${extension}` }
  usedNames.add(nextName.toLowerCase()); return nextName;
}
function isDownloadAbortError(value: unknown) { return value instanceof DOMException && value.name === 'AbortError' }
