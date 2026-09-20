<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import AppIcon from '@shared/components/AppIcon.vue';
import AppContextMenu from '@shared/components/context-menu/AppContextMenu.vue';
import type { ContextMenuEntry as FileContextMenuItem } from '@shared/components/context-menu/types';
import type { TerminalDownloadProtocol, TerminalFileEntry } from '../../types';
import {
  fileText,
  formatEntrySize,
  getEntryDirectoryPath,
  getEntryResolvedPath,
  getSftpSessionLoadPath,
  isParentEntry,
  type SftpCreateDialogState,
  type SftpFileUploadItem,
  type SftpPropertiesDialogState,
  type SftpSession,
  useSftpBrowser,
} from '../../composables/useSftpBrowser';
import { TERMINAL_FILE_ROW_HEIGHT } from '../../utils/virtualList';
import FileCreateDialog from './FileCreateDialog.vue';
import FileDownloadDialog from './FileDownloadDialog.vue';
import FilePropertiesDialog from './FilePropertiesDialog.vue';
import FileTable from './FileTable.vue';
import FileToolbar from './FileToolbar.vue';
import FileUploadDialog from './FileUploadDialog.vue';

interface Props {
  visible: boolean;
  active: boolean;
  sessionKey: string | null;
  hostId: number | null;
  currentCwd: string;
  nodeName: string;
  handleUnauthorized: (error: unknown) => boolean;
}
interface DroppedFileSystemEntry {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file?: (success: (file: File) => void, error?: (error: DOMException) => void) => void;
  createReader?: () => {
    readEntries(success: (entries: DroppedFileSystemEntry[]) => void, error?: (error: DOMException) => void): void;
  };
}
interface FileContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  entry: TerminalFileEntry | null;
}
interface DirectoryContextMenuState {
  visible: boolean;
  x: number;
  y: number;
}
interface FileMarqueeState {
  active: boolean;
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
  additive: boolean;
  basePaths: string[];
}
interface FileTableExpose {
  list: HTMLElement | null;
}
interface FileUploadExpose {
  openFile: () => void;
  openFolder: () => void;
}

const TRANSFER_PANEL_DEFAULT_HEIGHT = 170;
const TRANSFER_PANEL_MIN_HEIGHT = 96;
const TRANSFER_PANEL_MAX_HEIGHT = 360;

const props = defineProps<Props>();
const emit = defineEmits<{ writeTerminal: [text: string] }>();
const root = ref<HTMLElement | null>(null);
const fileTable = ref<FileTableExpose | null>(null);
const uploadDialog = ref<FileUploadExpose | null>(null);
const transferPanelHeight = ref(TRANSFER_PANEL_DEFAULT_HEIGHT);
const maxTransferPanelHeight = ref(TRANSFER_PANEL_MAX_HEIGHT);
const fileContextMenu = ref<FileContextMenuState>({ visible: false, x: 0, y: 0, entry: null });
const directoryContextMenu = ref<DirectoryContextMenuState>({ visible: false, x: 0, y: 0 });
const marquee = ref<FileMarqueeState>({
  active: false,
  startX: 0,
  startY: 0,
  currentX: 0,
  currentY: 0,
  additive: false,
  basePaths: [],
});
let shouldSuppressFileClick = false;
let resizeObserver: ResizeObserver | null = null;

const session = computed<SftpSession | null>(() => {
  if (!props.active || !props.sessionKey || props.hostId === null) return null;
  return { key: props.sessionKey, hostId: props.hostId, currentCwd: props.currentCwd };
});
const browser = useSftpBrowser({ session, onUnauthorized: props.handleUnauthorized });
const panelStyle = computed<Record<string, string>>(() => ({ '--terminal-transfer-height': `${transferPanelHeight.value}px` }));
const marqueeStyle = computed<Record<string, string>>(() => {
  const state = marquee.value;
  return {
    left: `${Math.min(state.startX, state.currentX)}px`,
    top: `${Math.min(state.startY, state.currentY)}px`,
    width: `${Math.abs(state.currentX - state.startX)}px`,
    height: `${Math.abs(state.currentY - state.startY)}px`,
  };
});
const fileContextMenuItems = computed<FileContextMenuItem[]>(() => {
  const entry = fileContextMenu.value.entry;
  const targetEntries = browser.actionEntries(entry);
  const isMultiple = targetEntries.length > 1;
  const isSingle = targetEntries.length === 1;
  const hasEntry = Boolean(entry);
  const isParent = isParentEntry(entry);
  const isDirectory = entry?.type === 'directory';
  const resolvedPath = entry ? getEntryResolvedPath(entry, browser.path.value) : '';
  const name = entry?.name ?? '';
  const directoryPath = entry ? getEntryDirectoryPath(entry, browser.path.value) : '';
  const targetPathsText = targetEntries.map((item) => getEntryResolvedPath(item, browser.path.value)).join('\n');
  const targetNamesText = targetEntries.map((item) => item.name).join('\n');
  return [
    { id: 'open', label: '打开', icon: 'folder', enabled: Boolean(isDirectory) && (isSingle || isParent), action: () => { if (entry) browser.openDirectory(entry); } },
    { id: 'refresh', label: '刷新', icon: 'refresh', enabled: true, action: () => browser.loadDirectory(browser.path.value, { force: true }) },
    { id: 'upload', label: '上传到当前文件夹...', icon: 'upload', enabled: hasEntry && !isParent, action: openUpload },
    { id: 'download', label: isMultiple ? '下载所选到目录...' : '下载到目录...', icon: 'download', enabled: targetEntries.length > 0, action: () => browser.downloadFiles(targetEntries) },
    { id: 'rename', label: '重命名...', icon: 'edit', enabled: hasEntry && !isParent && isSingle, separatorBefore: true, action: () => { if (entry) browser.startRename(entry); } },
    { id: 'move', label: '移动到...', icon: 'moveRight', enabled: false, action: () => undefined },
    { id: 'delete', label: isMultiple ? '删除所选' : '删除', icon: 'trash', enabled: targetEntries.length > 0, danger: true, action: () => browser.openDeleteDialog(targetEntries) },
    { id: 'favorite', label: '添加到收藏夹', icon: 'bookmark', enabled: false, separatorBefore: true, action: () => undefined },
    { id: 'copy-path', label: isMultiple ? '复制所选路径' : '复制路径', icon: 'copy', enabled: targetEntries.length > 0 || hasEntry, separatorBefore: true, action: () => copyText(targetEntries.length > 0 ? targetPathsText : resolvedPath) },
    { id: 'copy-name', label: isMultiple ? '复制所选名称' : '复制名称', icon: 'copy', enabled: targetEntries.length > 0, action: () => copyText(isMultiple ? targetNamesText : name) },
    { id: 'copy-directory', label: '复制目录路径', icon: 'folder', enabled: hasEntry && !isParent, action: () => copyText(directoryPath) },
    { id: 'send-path', label: isMultiple ? '将所选路径发送到终端' : '将路径发送到终端', icon: 'cornerDownLeft', enabled: targetEntries.length > 0 || hasEntry, separatorBefore: true, action: () => emit('writeTerminal', targetEntries.length > 0 ? targetPathsText : resolvedPath) },
    { id: 'send-name', label: isMultiple ? '将所选名称发送到终端' : '将名称发送到终端', icon: 'chevronRight', enabled: targetEntries.length > 0, action: () => emit('writeTerminal', isMultiple ? targetNamesText : name) },
    { id: 'send-directory', label: '将目录路径发送到终端', icon: 'chevronsRight', enabled: hasEntry && !isParent, action: () => emit('writeTerminal', directoryPath) },
    { id: 'properties', label: '属性...', icon: 'info', enabled: hasEntry && !isParent && isSingle, separatorBefore: true, action: async () => { if (entry) await browser.openProperties(entry); } },
  ];
});
const directoryContextMenuItems = computed<FileContextMenuItem[]>(() => [
  { id: 'refresh', label: '刷新', icon: 'refresh', enabled: props.active, action: () => browser.loadDirectory(browser.path.value, { force: true }) },
  {
    id: 'upload', label: '上传到当前文件夹...', icon: 'upload', enabled: props.active, action: () => undefined,
    children: [
      { id: 'upload-file', label: '上传文件', icon: 'file', enabled: props.active, action: openUpload },
      { id: 'upload-folder', label: '上传文件夹', icon: 'folder', enabled: props.active, action: openFolderUpload },
    ],
  },
  { id: 'create-file', label: '新建文件', icon: 'file', enabled: props.active, separatorBefore: true, action: () => browser.openCreateDialog('file') },
  { id: 'create-directory', label: '新建文件夹', icon: 'folderPlus', enabled: props.active, action: () => browser.openCreateDialog('directory') },
  { id: 'create-symlink', label: '新建符号链接', icon: 'link', enabled: props.active, action: () => browser.openCreateDialog('symlink') },
  { id: 'copy-directory', label: '复制目录路径', icon: 'copy', enabled: props.active, separatorBefore: true, action: () => copyText(browser.path.value) },
  { id: 'send-directory', label: '将目录路径发送到终端', icon: 'cornerDownLeft', enabled: props.active, action: () => emit('writeTerminal', browser.path.value) },
  { id: 'properties', label: '属性', icon: 'info', enabled: props.active, separatorBefore: true, action: () => browser.openCurrentDirectoryProperties() },
]);
const deleteEntries = computed(() => browser.deleteDialog.value.entries.length
  ? browser.deleteDialog.value.entries
  : browser.deleteDialog.value.entry ? [browser.deleteDialog.value.entry] : []);
const deleteVisualType = computed(() => {
  if (deleteEntries.value.length === 1) return deleteEntries.value[0].type;
  return deleteEntries.value.length > 0 && deleteEntries.value.every((entry) => entry.type === 'directory') ? 'directory' : 'file';
});
const deleteTitle = computed(() => deleteEntries.value.length > 1
  ? `确定要删除所选 ${deleteEntries.value.length} 项吗？`
  : `确定要删除“${deleteEntries.value[0]?.name ?? ''}”吗？`);
const deleteDescription = computed(() => {
  if (deleteEntries.value.length <= 1) {
    return `此操作会从远端主机删除该${deleteEntries.value[0]?.type === 'directory' ? '目录及其内容' : '文件'}。`;
  }
  const directoryCount = deleteEntries.value.filter((entry) => entry.type === 'directory').length;
  const fileCount = deleteEntries.value.length - directoryCount;
  if (directoryCount && fileCount) return `此操作会从远端主机删除 ${fileCount} 个文件和 ${directoryCount} 个目录及其内容。`;
  if (directoryCount) return `此操作会从远端主机删除 ${directoryCount} 个目录及其内容。`;
  return `此操作会从远端主机删除 ${fileCount} 个文件。`;
});

watch(
  () => [props.sessionKey, props.visible, props.active] as const,
  ([nextKey, nextVisible, nextActive], previous) => {
    const [previousKey, previousVisible, previousActive] = previous ?? [null, false, false];
    const sessionChanged = nextKey !== previousKey;
    const becameVisible = nextVisible && !previousVisible;
    const becameActive = nextActive && !previousActive;
    if (sessionChanged || becameVisible || becameActive) {
      const loadPath = getSftpSessionLoadPath(sessionChanged, browser.followingCwd.value, props.currentCwd);
      browser.reset('.');
      closeContextMenus();
      if (nextVisible && nextActive && nextKey) void browser.loadDirectory(loadPath);
      void nextTick(syncTransferPanelHeight);
    }
  },
  { immediate: true },
);
watch(() => props.currentCwd, (cwd) => browser.syncFollowedCwd(cwd));
watch(() => props.visible, (visible) => { if (!visible) closeContextMenus(); });

function selectEntry(entry: TerminalFileEntry, event: MouseEvent | KeyboardEvent) {
  if (shouldSuppressFileClick) {
    shouldSuppressFileClick = false;
    return;
  }
  browser.select(entry, event.shiftKey);
}
function openFileContextMenu(entry: TerminalFileEntry, event: MouseEvent) {
  if (!props.active) return;
  if (!browser.isSelected(entry)) browser.setSelection([entry], isParentEntry(entry) ? '' : entry.path);
  else browser.selectedEntry.value = entry;
  closeDirectoryContextMenu();
  fileContextMenu.value = { visible: true, x: event.clientX, y: event.clientY, entry };
}
function openDirectoryContextMenu(event: MouseEvent) {
  if (!props.active) return;
  const target = event.target as Element | null;
  if (target?.closest('.terminal-file-item') || target?.closest('.terminal-file-context-menu')) return;
  browser.setSelection([], '');
  closeFileContextMenu();
  directoryContextMenu.value = { visible: true, x: event.clientX, y: event.clientY };
}
function closeFileContextMenu() {
  fileContextMenu.value = { visible: false, x: 0, y: 0, entry: null };
}
function closeDirectoryContextMenu() {
  directoryContextMenu.value = { visible: false, x: 0, y: 0 };
}
function closeContextMenus() {
  closeFileContextMenu();
  closeDirectoryContextMenu();
}
async function runContextMenuItem(item: FileContextMenuItem) {
  if (!item.enabled || item.children?.length) return;
  closeContextMenus();
  await item.action();
}
async function copyText(value: string) {
  if (value) await navigator.clipboard?.writeText(value);
}
function openUpload() {
  if (!props.active || isParentEntry(browser.selectedEntry.value)) return;
  closeContextMenus();
  uploadDialog.value?.openFile();
}
function openFolderUpload() {
  if (!props.active) return;
  closeContextMenus();
  uploadDialog.value?.openFolder();
}
function changeCreateDialog(patch: Partial<SftpCreateDialogState>) {
  browser.createDialog.value = { ...browser.createDialog.value, ...patch };
}
function changePropertiesDialog(patch: Partial<SftpPropertiesDialogState>) {
  browser.propertiesDialog.value = { ...browser.propertiesDialog.value, ...patch };
}
function changeRenameName(name: string) {
  if (browser.rename.value) browser.rename.value = { ...browser.rename.value, draftName: name };
}
function changeDownloadProtocol(value: Event | TerminalDownloadProtocol) {
  browser.downloadProtocol.value = (
    typeof value === 'string' ? value : (value.target as HTMLSelectElement).value
  ) as TerminalDownloadProtocol;
}

function startMarquee(event: MouseEvent) {
  const list = fileTable.value?.list;
  if (!props.active || event.button !== 0 || !list) return;
  const target = event.target as Element | null;
  const currentTarget = event.currentTarget as Element | null;
  const isListBlank = target === currentTarget && currentTarget?.classList.contains('terminal-file-list');
  const isFileRow = currentTarget?.classList.contains('terminal-file-item') && !target?.closest('input');
  if (!isListBlank && !isFileRow) return;
  event.preventDefault();
  closeContextMenus();
  const point = listPoint(event);
  marquee.value = {
    active: true,
    startX: point.x,
    startY: point.y,
    currentX: point.x,
    currentY: point.y,
    additive: event.shiftKey || event.ctrlKey || event.metaKey,
    basePaths: Array.from(browser.selectedPaths.value),
  };
  updateMarqueeSelection();
  window.addEventListener('mousemove', moveMarquee);
  window.addEventListener('mouseup', stopMarquee);
}
function moveMarquee(event: MouseEvent) {
  if (!marquee.value.active) return;
  const point = listPoint(event);
  marquee.value = { ...marquee.value, currentX: point.x, currentY: point.y };
  updateMarqueeSelection();
}
function stopMarquee() {
  if (!marquee.value.active) return;
  const state = marquee.value;
  shouldSuppressFileClick = Math.abs(state.currentX - state.startX) > 4 || Math.abs(state.currentY - state.startY) > 4;
  updateMarqueeSelection();
  marquee.value = { ...state, active: false };
  window.removeEventListener('mousemove', moveMarquee);
  window.removeEventListener('mouseup', stopMarquee);
  window.setTimeout(() => { shouldSuppressFileClick = false; }, 0);
}
function listPoint(event: MouseEvent) {
  const list = fileTable.value?.list;
  if (!list) return { x: 0, y: 0 };
  const rect = list.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top + list.scrollTop };
}
function updateMarqueeSelection() {
  const list = fileTable.value?.list;
  if (!list) return;
  const state = marquee.value;
  const box = {
    left: Math.min(state.startX, state.currentX),
    right: Math.max(state.startX, state.currentX),
    top: Math.min(state.startY, state.currentY),
    bottom: Math.max(state.startY, state.currentY),
  };
  const intersectsListWidth = box.right >= 0 && box.left <= list.clientWidth;
  const firstIndex = Math.max(0, Math.floor(box.top / TERMINAL_FILE_ROW_HEIGHT));
  const lastIndex = Math.min(
    browser.entries.value.length - 1,
    Math.floor(box.bottom / TERMINAL_FILE_ROW_HEIGHT),
  );
  const selected = intersectsListWidth && lastIndex >= firstIndex
    ? browser.entries.value.slice(firstIndex, lastIndex + 1).filter((entry) => !isParentEntry(entry))
    : [];
  const nextPaths = new Set(state.additive ? state.basePaths : []);
  for (const entry of selected) nextPaths.add(entry.path);
  const nextEntries = browser.entries.value.filter((entry) => nextPaths.has(entry.path) && !isParentEntry(entry));
  browser.setSelection(nextEntries, nextEntries[0]?.path ?? '');
}

function startDragDownload(entry: TerminalFileEntry, event: DragEvent) {
  if (!props.active || entry.type !== 'file' || isParentEntry(entry) || !event.dataTransfer) return;
  if (!browser.isSelected(entry)) browser.setSelection([entry], entry.path);
  browser.selectedEntry.value = entry;
  const selectedFiles = browser.selectedEntries.value.filter((item) => item.type === 'file' && !isParentEntry(item));
  const entries = browser.isSelected(entry) && selectedFiles.length ? selectedFiles : [entry];
  const items = entries.map((item) => ({
    mimeType: 'application/octet-stream',
    filename: item.name,
    url: new URL(browser.getDownloadUrl(item), window.location.origin).toString(),
  }));
  event.dataTransfer.effectAllowed = 'copy';
  const first = items[0];
  event.dataTransfer.setData('DownloadURL', `${first.mimeType}:${first.filename}:${first.url}`);
  if (items.length === 1) {
    event.dataTransfer.setData('text/uri-list', first.url);
    event.dataTransfer.setData('text/plain', first.filename);
    return;
  }
  event.dataTransfer.setData('DownloadURL-list', JSON.stringify(items));
  event.dataTransfer.setData('text/uri-list', items.map((item) => item.url).join('\n'));
  event.dataTransfer.setData('text/plain', items.map((item) => item.filename).join('\n'));
}
function dragEnter(event: DragEvent) {
  if (!props.active || !hasLocalFiles(event)) return;
  event.preventDefault();
  browser.isDragOver.value = true;
}
function dragOver(event: DragEvent) {
  if (!props.active || !hasLocalFiles(event)) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  browser.isDragOver.value = true;
}
function dragLeave(event: DragEvent) {
  if (!(event.currentTarget instanceof HTMLElement)) return;
  const nextTarget = event.relatedTarget;
  if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) return;
  browser.isDragOver.value = false;
}
async function dropFiles(event: DragEvent) {
  if (!props.active || !hasLocalFiles(event)) return;
  event.preventDefault();
  browser.isDragOver.value = false;
  const items = await droppedUploadItems(event);
  if (items.length) await browser.uploadFiles(items);
}
function hasLocalFiles(event: DragEvent) {
  return Array.from(event.dataTransfer?.types || []).includes('Files');
}
async function droppedUploadItems(event: DragEvent): Promise<SftpFileUploadItem[]> {
  const entries = Array.from(event.dataTransfer?.items || [])
    .map(getDroppedFileSystemEntry)
    .filter((entry): entry is DroppedFileSystemEntry => Boolean(entry));
  if (entries.length) return (await Promise.all(entries.map((entry) => readDroppedEntry(entry)))).flat();
  return Array.from(event.dataTransfer?.files || []).map((file) => ({
    file,
    relativePath: (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name,
  }));
}
function getDroppedFileSystemEntry(item: DataTransferItem): DroppedFileSystemEntry | null {
  const entryItem = item as DataTransferItem & { webkitGetAsEntry?: () => DroppedFileSystemEntry | null };
  return entryItem.webkitGetAsEntry?.() ?? null;
}
async function readDroppedEntry(entry: DroppedFileSystemEntry, parentPath = ''): Promise<SftpFileUploadItem[]> {
  const relativePath = parentPath ? `${parentPath}/${entry.name}` : entry.name;
  if (entry.isFile && entry.file) return [{ file: await readDroppedFile(entry), relativePath }];
  if (!entry.isDirectory || !entry.createReader) return [];
  const children = await readDroppedDirectoryEntries(entry);
  return (await Promise.all(children.map((child) => readDroppedEntry(child, relativePath)))).flat();
}
function readDroppedFile(entry: DroppedFileSystemEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file?.(resolve, reject));
}
function readDroppedDirectoryEntries(entry: DroppedFileSystemEntry): Promise<DroppedFileSystemEntry[]> {
  const reader = entry.createReader?.();
  if (!reader) return Promise.resolve([]);
  const entries: DroppedFileSystemEntry[] = [];
  return new Promise((resolve, reject) => {
    const readBatch = () => reader.readEntries((batch) => {
      if (!batch.length) return resolve(entries);
      entries.push(...batch);
      readBatch();
    }, reject);
    readBatch();
  });
}

function setTransferPanelHeight(height: number) {
  transferPanelHeight.value = Math.min(Math.max(height, TRANSFER_PANEL_MIN_HEIGHT), maxTransferPanelHeight.value);
}
function syncTransferPanelHeight() {
  const height = root.value?.getBoundingClientRect().height ?? 0;
  const maxByPanel = height ? Math.floor(height * 0.45) : TRANSFER_PANEL_MAX_HEIGHT;
  maxTransferPanelHeight.value = Math.max(TRANSFER_PANEL_MIN_HEIGHT, Math.min(TRANSFER_PANEL_MAX_HEIGHT, maxByPanel));
  setTransferPanelHeight(transferPanelHeight.value);
}
function onWindowClick() {
  closeContextMenus();
}
function onWindowKeydown(event: KeyboardEvent) {
  if ((event.target as Element | null)?.closest('.shadcn-context-menu-content')) return;
  if (event.key !== 'Escape') return;
  closeContextMenus();
  browser.closeDialogs();
}

onMounted(() => {
  window.addEventListener('click', onWindowClick);
  window.addEventListener('keydown', onWindowKeydown);
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(syncTransferPanelHeight);
    if (root.value) resizeObserver.observe(root.value);
  }
  syncTransferPanelHeight();
});
onBeforeUnmount(() => {
  window.removeEventListener('click', onWindowClick);
  window.removeEventListener('keydown', onWindowKeydown);
  window.removeEventListener('mousemove', moveMarquee);
  window.removeEventListener('mouseup', stopMarquee);
  resizeObserver?.disconnect();
  browser.cancelAllTransfers();
});
</script>

<template>
  <div v-show="visible" ref="root" class="terminal-file-browser" :style="panelStyle">
    <header class="terminal-file-title">
      <strong>文件浏览器</strong>
      <span class="terminal-file-node">{{ nodeName }}</span>
    </header>
    <FileToolbar
      :can-download="browser.canDownloadSelection.value"
      :selected-count="browser.selectedCount.value"
      @create="browser.openCreateDialog"
      @upload="openUpload"
      @download="browser.downloadFiles()"
      @delete="browser.openDeleteDialog()"
      @parent="browser.openParentDirectory"
      @refresh="browser.loadDirectory(browser.path.value, { force: true })"
    />
    <AppContextMenu
      :open="fileContextMenu.visible || directoryContextMenu.visible"
      :items="fileContextMenu.visible ? fileContextMenuItems : directoryContextMenuItems"
      :disabled="!active"
      @update:open="!$event && closeContextMenus()"
      @select="runContextMenuItem"
    >
      <div
        style="display: contents"
        @contextmenu="!($event.target as Element).closest('.terminal-file-list') && $event.preventDefault()"
      >
        <FileTable
          ref="fileTable"
          :active="active"
          :path="browser.path.value"
          :entries="browser.entries.value"
          :selected-paths="browser.selectedPaths.value"
          :loading="browser.isLoading.value"
          :error="browser.error.value"
          :drag-over="browser.isDragOver.value"
          :marquee-active="marquee.active"
          :marquee-style="marqueeStyle"
          :rename="browser.rename.value"
          :format-size="formatEntrySize"
          :text="fileText"
          :is-parent="isParentEntry"
          @select="selectEntry"
          @entry-context="openFileContextMenu"
          @directory-context="openDirectoryContextMenu"
          @marquee-start="startMarquee"
          @drag-start="startDragDownload"
          @open="browser.openDirectory"
          @drag-enter="dragEnter"
          @drag-over="dragOver"
          @drag-leave="dragLeave"
          @drop="dropFiles"
          @rename-name="changeRenameName"
          @save-rename="browser.saveRename"
          @cancel-rename="browser.cancelRename"
        />
      </div>
    </AppContextMenu>
    <footer class="terminal-file-status">
      <span>{{ browser.selectionStatusText.value }}</span>
      <span class="terminal-file-protocol" :class="browser.status.value">{{ browser.statusText.value }}</span>
      <label class="terminal-file-download-protocol" :title="`下载方式：${browser.downloadProtocol.value === 'auto' ? '自动' : browser.downloadProtocol.value.toUpperCase()}`">
        <span>下载</span>
        <el-select :model-value="browser.downloadProtocol.value" aria-label="下载方式" size="small" @change="changeDownloadProtocol">
          <el-option value="auto" label="自动" />
          <el-option value="sftp" label="SFTP" />
          <el-option value="scp" label="SCP" />
        </el-select>
      </label>
      <div>
        <el-button
          circle
          :title="browser.followCwdLabel.value"
          :aria-label="browser.followCwdLabel.value"
          :aria-pressed="browser.followingCwd.value"
          :class="{ active: browser.followingCwd.value }"
          @click="browser.toggleFollowCwd"
        >
          <AppIcon name="refresh" :size="15" />
        </el-button>
      </div>
    </footer>
    <FileDownloadDialog
      :records="browser.transferRecords.value"
      :has-running="browser.hasRunningTransfers.value"
      :has-clearable="browser.hasClearableTransfers.value"
      :height="transferPanelHeight"
      :max-height="maxTransferPanelHeight"
      @cancel="browser.cancelTransfer"
      @cancel-all="browser.cancelAllTransfers"
      @clear="browser.clearTransferRecords"
      @resize="setTransferPanelHeight"
    />
    <FileUploadDialog ref="uploadDialog" @selected="browser.uploadFiles" />


    <el-dialog
      :model-value="browser.deleteDialog.value.visible"
      class="terminal-file-delete-backdrop"
      width="460px"
      :show-close="false"
      :close-on-click-modal="false"
      @close="browser.closeDeleteDialog"
    >
      <div class="popup-body terminal-file-delete-body">
        <section class="terminal-file-delete-modal">
          <div class="terminal-file-delete-visual" :class="deleteVisualType">
            <span class="terminal-file-delete-visual-card"><AppIcon :name="deleteVisualType === 'directory' ? 'folder' : 'file'" :size="34" /></span>
            <span class="terminal-file-delete-alert"><AppIcon name="alert" :size="18" /></span>
          </div>
          <h2>{{ deleteTitle }}</h2>
          <p>{{ deleteDescription }}</p>
          <el-alert v-if="browser.deleteDialog.value.error" class="terminal-file-delete-error" type="error" :title="browser.deleteDialog.value.error" :closable="false" />
          <div class="terminal-file-delete-actions popup-actions">
            <el-button :disabled="browser.deleteDialog.value.deleting" @click="browser.closeDeleteDialog">取消</el-button>
            <el-button type="danger" :loading="browser.deleteDialog.value.deleting" :disabled="browser.deleteDialog.value.deleting" @click="browser.confirmDelete">
              {{ browser.deleteDialog.value.deleting ? '删除中...' : '删除' }}
            </el-button>
          </div>
        </section>
      </div>
    </el-dialog>
    <FileCreateDialog
      :dialog="browser.createDialog.value"
      :title="browser.createTitle()"
      :name-label="browser.createNameLabel()"
      :open-label="browser.createOpenLabel()"
      @change="changeCreateDialog"
      @close="browser.closeCreateDialog"
      @save="browser.saveCreateDialog"
    />
    <FilePropertiesDialog
      :dialog="browser.propertiesDialog.value"
      @change="changePropertiesDialog"
      @close="browser.closePropertiesDialog"
      @save="browser.saveProperties"
    />
  </div>
</template>
