<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';

import { useAppContext } from '@app/context';
import AppIcon from '@shared/components/AppIcon.vue';
import AppPagination from '@shared/components/AppPagination.vue';
import { errorMessage } from '@shared/utils/errors';
import {
  cancelBulkExecutionTask,
  checkBulkFileUpload,
  createBulkExecutionTask,
  createBulkFileUploadTask,
  deleteBulkExecutionTask,
  getBulkExecutionTask,
  listBulkExecutionTargetTree,
  listBulkExecutionTasks,
} from '../api/bulkExecution';
import type {
  BulkExecutionResult,
  BulkExecutionResultStatus,
  BulkExecutionStatus,
  BulkExecutionTarget,
  BulkExecutionTargetGroup,
  BulkExecutionTask,
  BulkExecutionTaskDetail,
  BulkExecutionType,
  BulkExecutionUploadFile,
  BulkTransferItem,
  BulkUploadCheckResult,
} from '../types';

type BulkView = 'history' | 'execute' | 'upload';
type UploadDetailView = 'hosts' | 'files' | 'directory';
type TargetGroupRow = { group: BulkExecutionTargetGroup; level: number; hasChildren: boolean; expanded: boolean };
type UploadFileTreeNode = {
  key: string;
  name: string;
  type: 'directory' | 'file';
  level: number;
  size: number;
  file?: BulkExecutionUploadFile;
  children: UploadFileTreeNode[];
};
type UploadFileTreeRow = UploadFileTreeNode & { expanded: boolean; hasChildren: boolean };

const DRAFT_TARGET_IDS_KEY = 'ops-tool.bulk-execution.draft-target-ids';
const uploadTargetIdsKey = 'ops-tool.bulk-execution.upload-target-ids';

const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  canceled: '已取消',
  pending: '等待中',
  success: '成功',
  skipped: '已跳过',
};

const historyStatusOptions: Array<{ value: BulkExecutionStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'queued', label: '未开始' },
  { value: 'running', label: '执行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '异常' },
  { value: 'canceled', label: '已停止' },
];

const executionTypeLabels: Record<BulkExecutionType, string> = {
  shell: '普通 Shell',
  file_upload: '文件上传',
};

const scriptPresets: Array<{ key: string; label: string; type: Exclude<BulkExecutionType, 'file_upload'>; command: string }> = [
  { key: 'shell-health', label: '系统巡检', type: 'shell', command: 'hostname\nuptime\ndf -h\nfree -m' },
  { key: 'shell-service', label: '服务状态', type: 'shell', command: 'systemctl status nginx --no-pager || true' },
];

const MAX_SCRIPT_LENGTH = 200000;

const { activeTool, canUsePageAction, showToast, requestConfirm } = useAppContext();

const activeBulkView = ref<BulkView>('history');
const targets = ref<BulkExecutionTarget[]>([]);
const targetGroups = ref<BulkExecutionTargetGroup[]>([]);
const taskHistory = ref<BulkExecutionTask[]>([]);
const taskTotal = ref(0);
const taskPage = ref(1);
const taskPageSize = ref(10);
const selectedTask = ref<BulkExecutionTaskDetail | null>(null);
const selectedTaskId = ref<number | null>(null);
const selectedRecordTaskIds = ref<Set<number>>(new Set());
const selectedTargetIds = ref<Set<number>>(new Set());
const isTargetPickerOpen = ref(false);
const draftTargetIds = ref<Set<number>>(new Set());
const targetGroupFilter = ref<number | null>(null);
const targetPickerKeyword = ref('');
const collapsedTargetGroups = ref<Set<number>>(new Set());
const expandedResultIds = ref<Set<number>>(new Set());
const uploadDetailView = ref<UploadDetailView>('hosts');
const expandedUploadFolderKeys = ref<Set<string>>(new Set());
const isTaskDetailOpen = ref(false);
const isLoading = ref(false);
const isTargetsLoading = ref(false);
const isCreating = ref(false);
const isUploading = ref(false);
const isCheckingUpload = ref(false);
const isControlBusy = ref(false);
const uploadFileInput = ref<HTMLInputElement | null>(null);
const uploadFolderInput = ref<HTMLInputElement | null>(null);
const scriptFileInput = ref<HTMLInputElement | null>(null);
const keyword = ref('');
const statusFilter = ref('');
const hostFilter = ref<number | ''>('');
const taskName = ref('');
const executionType = ref<Exclude<BulkExecutionType, 'file_upload'>>('shell');
const commandInput = ref('');
const scriptSourceName = ref('');
const selectedUploadFiles = ref<File[]>([]);
const remoteDirectory = ref('/tmp/');
const uploadCheckResult = ref<BulkUploadCheckResult | null>(null);
const overwriteConfirmed = ref(false);
let pollTimer: number | null = null;
const pollInFlight = ref(false);
let taskRequestId = 0;

const canExecute = computed(() => canUsePageAction('bulkExecution', 'execute'));
const canRefresh = computed(() => canUsePageAction('bulkExecution', 'refresh'));
const canCancel = computed(() => canUsePageAction('bulkExecution', 'cancel'));
const canDelete = computed(() => canUsePageAction('bulkExecution', 'delete'));
const hasRunningTask = computed(() => taskHistory.value.some((task) => task.status === 'queued' || task.status === 'running'));
const selectedTargets = computed(() => targets.value.filter((target) => selectedTargetIds.value.has(target.id)));
const draftSelectedTargets = computed(() => targets.value.filter((target) => draftTargetIds.value.has(target.id)));
const targetGroupRows = computed<TargetGroupRow[]>(() => flattenTargetGroupRows(targetGroups.value));
const activeTargetGroupIds = computed(() => {
  if (targetGroupFilter.value === null) return null;
  const group = findTargetGroup(targetGroups.value, targetGroupFilter.value);
  return group ? collectTargetGroupIds(group) : null;
});
const pickerTargets = computed(() => {
  const query = targetPickerKeyword.value.trim().toLowerCase();
  return targets.value.filter((target) => {
    if (activeTargetGroupIds.value && !activeTargetGroupIds.value.has(target.group)) return false;
    if (!query) return true;
    return [target.name, target.privateIp, target.publicIp, target.groupName, target.loginUser, target.os, target.systemType, target.systemArch]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
});
const allPickerTargetsSelected = computed(() => pickerTargets.value.length > 0 && pickerTargets.value.every((target) => draftTargetIds.value.has(target.id)));
const uploadTotalSize = computed(() => selectedUploadFiles.value.reduce((total, file) => total + file.size, 0));
const duplicateFiles = computed(() => uploadCheckResult.value?.duplicateFiles ?? []);
const unreachableTargets = computed(() => uploadCheckResult.value?.unreachableTargets ?? []);
const usableUploadTargetIds = computed(() => uploadCheckResult.value?.usableTargetIds ?? [...selectedTargetIds.value]);
const uploadHasWarnings = computed(() => duplicateFiles.value.length > 0 || unreachableTargets.value.length > 0);
const canCreateTask = computed(() => canExecute.value && !isCreating.value);
const canCheckUpload = computed(() => canExecute.value && !isCheckingUpload.value && !isUploading.value);
const canCreateUpload = computed(() => canExecute.value && !isCheckingUpload.value && !isUploading.value);
const taskTotalPages = computed(() => Math.max(1, Math.ceil(taskTotal.value / taskPageSize.value)));
const taskPageStart = computed(() => (taskTotal.value ? (taskPage.value - 1) * taskPageSize.value + 1 : 0));
const visibleRecordTaskIds = computed(() => taskHistory.value.map((task) => task.id));
const allVisibleRecordsSelected = computed(() => visibleRecordTaskIds.value.length > 0 && visibleRecordTaskIds.value.every((id) => selectedRecordTaskIds.value.has(id)));
const someVisibleRecordsSelected = computed(() => visibleRecordTaskIds.value.some((id) => selectedRecordTaskIds.value.has(id)));
const selectedTaskCanCancel = computed(() => Boolean(selectedTask.value && ['queued', 'running'].includes(selectedTask.value.status)));
const selectedTaskProgress = computed(() => {
  if (!selectedTask.value || selectedTask.value.targetCount <= 0) return 0;
  return Math.round((selectedTask.value.completedCount / selectedTask.value.targetCount) * 100);
});
const selectedTaskUploadSize = computed(() => selectedTask.value?.uploadSize || selectedTask.value?.uploadFiles.reduce((total, file) => total + file.size, 0) || 0);
const uploadFileTreeRows = computed(() => flattenUploadFileTree(buildUploadFileTree(selectedTask.value?.uploadFiles ?? []), expandedUploadFolderKeys.value));
const selectedTaskExecutionType = computed(() => selectedTask.value ? executionTypeLabels[selectedTask.value.executionType] : '');
const selectedTaskResultIds = computed(() => selectedTask.value?.results.map((result) => result.id) ?? []);
const allResultsExpanded = computed(() => selectedTaskResultIds.value.length > 0 && selectedTaskResultIds.value.every((id) => expandedResultIds.value.has(id)));
const canClearScriptInput = computed(() => Boolean(commandInput.value.trim() || scriptSourceName.value));
const commandPlaceholder = 'set -e\nhostname\nuptime';
const scriptFileAccept = '.sh';
const scriptUploadButtonLabel = '上传 SH';
const executeActionLabel = '执行 Shell';

onMounted(async () => {
  await refreshAll();
  applyDraftTargetIds();
  applyUploadTargetIds();
  startPolling();
});

onUnmounted(() => {
  stopPolling();
});

watch([selectedUploadFiles, remoteDirectory, selectedTargetIds], () => {
  uploadCheckResult.value = null;
  overwriteConfirmed.value = false;
});

watch(
  () => activeTool.value,
  (tool) => {
    if (tool === 'bulkExecution') {
      void refreshAll().then(() => {
        applyDraftTargetIds();
        applyUploadTargetIds();
      });
    }
  },
);

async function refreshAll() {
  if (!canRefresh.value && !canExecute.value) return;
  isLoading.value = true;
  try {
    await Promise.all([loadTargets(), loadTasks()]);
  } finally {
    isLoading.value = false;
  }
}

async function loadTargets() {
  if (!canExecute.value) return;
  isTargetsLoading.value = true;
  try {
    const tree = await listBulkExecutionTargetTree();
    targets.value = tree.targets;
    targetGroups.value = tree.groups;
    if (targetGroupFilter.value !== null && !findTargetGroup(targetGroups.value, targetGroupFilter.value)) targetGroupFilter.value = null;
  } catch (error) {
    showToast('目标主机加载失败', errorMessage(error), 'error');
  } finally {
    isTargetsLoading.value = false;
  }
}

async function loadTasks() {
  if (!canRefresh.value) return;
  try {
    const page = await listBulkExecutionTasks({
      status: statusFilter.value,
      keyword: keyword.value.trim(),
      host: hostFilter.value,
      page: taskPage.value,
      pageSize: taskPageSize.value,
    });
    taskTotal.value = page.count;
    if (taskPage.value > taskTotalPages.value) {
      taskPage.value = taskTotalPages.value;
      await loadTasks();
      return;
    }
    taskHistory.value = page.results;
    syncSelectedRecordTasks();
    if (!taskHistory.value.length) {
      selectedTaskId.value = null;
      selectedTask.value = null;
      selectedRecordTaskIds.value = new Set();
      expandedResultIds.value = new Set();
      resetUploadDetailView();
      return;
    }
    if (!selectedTaskId.value || !taskHistory.value.some((task) => task.id === selectedTaskId.value)) {
      selectedTaskId.value = taskHistory.value[0].id;
    }
  } catch (error) {
    showToast('任务历史加载失败', errorMessage(error), 'error');
  }
}

async function selectTask(taskId: number, showError = true, activateHistory = true) {
  const requestId = ++taskRequestId;
  const shouldResetUploadDetail = selectedTask.value?.id !== taskId;
  selectedTaskId.value = taskId;
  if (activateHistory) activeBulkView.value = 'history';
  try {
    const detail = await getBulkExecutionTask(taskId);
    if (requestId !== taskRequestId || selectedTaskId.value !== taskId) return;
    selectedTask.value = {
      ...detail,
      uploadFiles: detail.uploadFiles ?? [],
      results: detail.results.map((result) => ({ ...result, transfers: result.transfers ?? [] })),
    };
    if (shouldResetUploadDetail) resetUploadDetailView();
    expandedResultIds.value = new Set([...expandedResultIds.value].filter((id) => detail.results.some((result) => result.id === id)));
  } catch (error) {
    if (requestId !== taskRequestId || selectedTaskId.value !== taskId) return;
    selectedTask.value = null;
    resetUploadDetailView();
    if (showError) showToast('任务详情加载失败', errorMessage(error), 'error');
  }
}

async function openTaskDetail(taskId: number) {
  resetUploadDetailView();
  await selectTask(taskId, true, false);
  if (selectedTask.value?.id === taskId) isTaskDetailOpen.value = true;
}

function closeTaskDetail() {
  isTaskDetailOpen.value = false;
}

function resetUploadDetailView() {
  uploadDetailView.value = 'hosts';
  expandedUploadFolderKeys.value = new Set();
}

function setUploadDetailView(view: UploadDetailView) {
  uploadDetailView.value = view;
}

function applyDraftTargetIds() {
  const ids = consumeHandoffIds(DRAFT_TARGET_IDS_KEY);
  if (!ids) return;
  applyHandoffTargets(ids, 'execute');
}

function applyUploadTargetIds() {
  const ids = consumeHandoffIds(uploadTargetIdsKey);
  if (!ids) return;
  applyHandoffTargets(ids, 'upload');
}

function consumeHandoffIds(key: string) {
  if (typeof window === 'undefined') return null;
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  window.sessionStorage.removeItem(key);
  try {
    const ids = JSON.parse(raw);
    return Array.isArray(ids) ? ids.map((id) => Number(id)) : null;
  } catch {
    return null;
  }
}

function applyHandoffTargets(ids: number[], view: BulkView) {
  const executableIds = new Set(targets.value.map((target) => target.id));
  const next = ids.filter((id) => executableIds.has(id));
  if (!next.length) {
    showToast(view === 'upload' ? '没有可上传主机' : '没有可执行主机', '所选主机中没有已验证的 Linux SSH 主机。', 'error');
    return;
  }
  selectedTargetIds.value = new Set(next);
  activeBulkView.value = view;
}

function switchBulkView(view: BulkView) {
  activeBulkView.value = view;
}

function setHistoryStatus(status: BulkExecutionStatus | '') {
  statusFilter.value = status;
  applyHistoryFilters();
}

function applyHistoryFilters() {
  taskPage.value = 1;
  selectedRecordTaskIds.value = new Set();
  void loadTasks();
}

function setTaskPage(nextPage: number) {
  const normalized = Math.min(Math.max(1, nextPage), taskTotalPages.value);
  if (taskPage.value === normalized) return;
  taskPage.value = normalized;
  selectedRecordTaskIds.value = new Set();
  void loadTasks();
}

function checkedFromControl(value: Event | boolean | string | number) {
  if (value instanceof Event) return (value.target as HTMLInputElement).checked;
  return Boolean(value);
}

function setTaskPageSize(value: Event | number | string) {
  taskPageSize.value = Number(value instanceof Event ? (value.target as HTMLSelectElement).value : value);
  taskPage.value = 1;
  selectedRecordTaskIds.value = new Set();
  void loadTasks();
}

function syncSelectedRecordTasks() {
  const visibleIds = new Set(taskHistory.value.map((task) => task.id));
  selectedRecordTaskIds.value = new Set([...selectedRecordTaskIds.value].filter((id) => visibleIds.has(id)));
}

function toggleRecordTaskSelection(taskId: number, value: Event | boolean | string | number) {
  const checked = checkedFromControl(value);
  const next = new Set(selectedRecordTaskIds.value);
  if (checked) next.add(taskId);
  else next.delete(taskId);
  selectedRecordTaskIds.value = next;
}

function toggleAllVisibleRecordTasks(value: Event | boolean | string | number) {
  const checked = checkedFromControl(value);
  const next = new Set(selectedRecordTaskIds.value);
  for (const id of visibleRecordTaskIds.value) {
    if (checked) next.add(id);
    else next.delete(id);
  }
  selectedRecordTaskIds.value = next;
}

function clearSelectedRecordTasks() {
  selectedRecordTaskIds.value = new Set();
}

function openCreateDialog() {
  switchBulkView('execute');
}

function openUploadDialog() {
  switchBulkView('upload');
}

function flattenTargetGroupRows(groups: BulkExecutionTargetGroup[], level = 0): TargetGroupRow[] {
  return groups.flatMap((group) => {
    const children = group.children ?? [];
    const expanded = !collapsedTargetGroups.value.has(group.key);
    const row: TargetGroupRow = { group, level, hasChildren: children.length > 0, expanded };
    return expanded ? [row, ...flattenTargetGroupRows(children, level + 1)] : [row];
  });
}

function findTargetGroup(groups: BulkExecutionTargetGroup[], groupId: number): BulkExecutionTargetGroup | null {
  for (const group of groups) {
    if (group.key === groupId) return group;
    const child = findTargetGroup(group.children ?? [], groupId);
    if (child) return child;
  }
  return null;
}

function collectTargetGroupIds(group: BulkExecutionTargetGroup): Set<number> {
  const ids = new Set<number>([group.key]);
  for (const child of group.children ?? []) {
    for (const id of collectTargetGroupIds(child)) ids.add(id);
  }
  return ids;
}

function buildUploadFileTree(files: BulkExecutionUploadFile[]): UploadFileTreeNode[] {
  const root: UploadFileTreeNode = { key: '', name: '', type: 'directory', level: -1, size: 0, children: [] };
  const folders = new Map<string, UploadFileTreeNode>([['', root]]);

  for (const file of files) {
    const parts = String(file.filename || '').replace(/\\/g, '/').split('/').filter(Boolean);
    const pathParts = parts.length ? parts : [file.filename || '-'];
    let parent = root;
    let currentPath = '';

    pathParts.forEach((part, index) => {
      const isFile = index === pathParts.length - 1;
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      if (isFile) {
        parent.children.push({
          key: `file:${file.id}:${currentPath}`,
          name: part,
          type: 'file',
          level: index,
          size: file.size,
          file,
          children: [],
        });
        return;
      }

      let folder = folders.get(currentPath);
      if (!folder) {
        folder = {
          key: currentPath,
          name: part,
          type: 'directory',
          level: index,
          size: 0,
          children: [],
        };
        folders.set(currentPath, folder);
        parent.children.push(folder);
      }
      folder.size += file.size;
      parent = folder;
    });
  }

  return root.children;
}

function flattenUploadFileTree(nodes: UploadFileTreeNode[], expandedKeys: Set<string>): UploadFileTreeRow[] {
  const rows: UploadFileTreeRow[] = [];
  const visit = (node: UploadFileTreeNode) => {
    const expanded = expandedKeys.has(node.key);
    rows.push({ ...node, expanded, hasChildren: node.children.length > 0 });
    if (node.type === 'directory' && expanded) node.children.forEach(visit);
  };
  nodes.forEach(visit);
  return rows;
}

function toggleUploadFolder(row: UploadFileTreeNode) {
  if (row.type !== 'directory' || !row.children.length) return;
  const next = new Set(expandedUploadFolderKeys.value);
  if (next.has(row.key)) next.delete(row.key);
  else next.add(row.key);
  expandedUploadFolderKeys.value = next;
}

function openTargetPicker() {
  draftTargetIds.value = new Set(selectedTargetIds.value);
  targetPickerKeyword.value = '';
  targetGroupFilter.value = null;
  isTargetPickerOpen.value = true;
}

function closeTargetPicker() {
  draftTargetIds.value = new Set(selectedTargetIds.value);
  isTargetPickerOpen.value = false;
}

function confirmTargetSelection() {
  selectedTargetIds.value = new Set(draftTargetIds.value);
  isTargetPickerOpen.value = false;
}

function selectTargetGroup(groupId: number | null) {
  targetGroupFilter.value = groupId;
}

function toggleTargetGroupCollapsed(groupId: number) {
  const next = new Set(collapsedTargetGroups.value);
  if (next.has(groupId)) next.delete(groupId);
  else next.add(groupId);
  collapsedTargetGroups.value = next;
}

function toggleDraftTarget(targetId: number, checked: boolean) {
  const next = new Set(draftTargetIds.value);
  if (checked) next.add(targetId);
  else next.delete(targetId);
  draftTargetIds.value = next;
}

function toggleAllPickerTargets(checked: boolean) {
  const next = new Set(draftTargetIds.value);
  for (const target of pickerTargets.value) {
    if (checked) next.add(target.id);
    else next.delete(target.id);
  }
  draftTargetIds.value = next;
}

function toggleDraftTargetFromEvent(targetId: number, value: Event | boolean | string | number) {
  toggleDraftTarget(targetId, checkedFromControl(value));
}

function toggleAllPickerTargetsFromEvent(value: Event | boolean | string | number) {
  toggleAllPickerTargets(checkedFromControl(value));
}

function removeSelectedTarget(targetId: number) {
  const next = new Set(selectedTargetIds.value);
  next.delete(targetId);
  selectedTargetIds.value = next;
}

function clearSelectedTargets() {
  selectedTargetIds.value = new Set();
}

function showMissingField(message: string) {
  showToast('请填写必填项', message, 'error');
  return false;
}

function validateExecuteForm() {
  if (!(taskName.value.trim().length > 0)) return showMissingField('请填写任务名称');
  if (!selectedTargetIds.value.size) return showMissingField('请选择目标机器');
  if (!commandInput.value.trim()) return showMissingField('请填写脚本内容');
  return true;
}

function validateUploadForm() {
  if (!(taskName.value.trim().length > 0)) return showMissingField('请填写任务名称');
  if (!selectedTargetIds.value.size) return showMissingField('请选择目标机器');
  if (!selectedUploadFiles.value.length) return showMissingField('请选择上传文件或文件夹');
  if (!remoteDirectory.value.trim()) return showMissingField('请填写远程目录');
  return true;
}

function createTaskWithConfirmation() {
  if (!canCreateTask.value) return;
  if (!validateExecuteForm()) return;
  const run = async () => {
    await createTask();
  };
  const message = `将对 ${selectedTargetIds.value.size} 台主机执行批量任务。`;
  if (requestConfirm) requestConfirm('确认批量执行', message, executeActionLabel.value, run);
  else if (window.confirm(message)) void run();
}

async function createTask() {
  isCreating.value = true;
  try {
    const task = await createBulkExecutionTask({
      targetIds: [...selectedTargetIds.value],
      command: commandInput.value,
      executionType: executionType.value,
      name: taskName.value.trim(),
    });
    taskName.value = '';
    executionType.value = 'shell';
    commandInput.value = '';
    scriptSourceName.value = '';
    selectedTargetIds.value = new Set();
    taskPage.value = 1;
    await loadTasks();
    await selectTask(task.id);
    showToast('批量执行已创建', '后台正在并发执行所选主机命令。', 'success');
  } catch (error) {
    showToast('任务创建失败', errorMessage(error), 'error');
  } finally {
    isCreating.value = false;
  }
}

function rerunTask(task: BulkExecutionTaskDetail) {
  if (task.executionType === 'file_upload') {
    switchBulkView('upload');
    taskName.value = task.name;
    remoteDirectory.value = task.remoteDirectory || '/tmp/';
    scriptSourceName.value = '';
  } else {
    executionType.value = task.executionType;
    commandInput.value = task.command;
    scriptSourceName.value = '';
    taskName.value = task.name;
    switchBulkView('execute');
  }
  selectedTargetIds.value = new Set(task.results.map((result) => result.host).filter((id): id is number => typeof id === 'number'));
}

async function rerunTaskFromList(taskId: number) {
  await selectTask(taskId, true, false);
  if (selectedTask.value) rerunTask(selectedTask.value);
}

async function deleteTaskFromList(taskId: number) {
  await selectTask(taskId, true, false);
  deleteSelectedTask();
}

function triggerScriptFileSelect() {
  scriptFileInput.value?.click();
}

function clearScriptInput() {
  commandInput.value = '';
  scriptSourceName.value = '';
}

async function onScriptFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  if (!isScriptFileAllowed(file.name)) {
    showToast('脚本类型不匹配', '请上传 .sh 脚本文件。', 'error');
    return;
  }
  try {
    const content = await file.text();
    if (content.length > MAX_SCRIPT_LENGTH) {
      showToast('脚本过长', `脚本内容不能超过 ${MAX_SCRIPT_LENGTH} 个字符。`, 'error');
      return;
    }
    commandInput.value = content;
    scriptSourceName.value = file.name;
  } catch (error) {
    showToast('脚本读取失败', errorMessage(error), 'error');
  }
}

function isScriptFileAllowed(fileName: string) {
  const normalized = fileName.toLowerCase();
  return /\.sh$/.test(normalized);
}

function triggerUploadFileSelect() {
  uploadFileInput.value?.click();
}

function triggerUploadFolderSelect() {
  uploadFolderInput.value?.click();
}

function onUploadFileChange(event: Event) {
  if (isUploading.value) return;
  const files = Array.from((event.target as HTMLInputElement).files ?? []);
  if (files.length) {
    selectedUploadFiles.value = mergeFiles(selectedUploadFiles.value, files);
  }
  (event.target as HTMLInputElement).value = '';
}

function onUploadFolderChange(event: Event) {
  if (isUploading.value) return;
  const files = Array.from((event.target as HTMLInputElement).files ?? []);
  if (files.length) {
    selectedUploadFiles.value = mergeFiles(selectedUploadFiles.value, files);
  }
  (event.target as HTMLInputElement).value = '';
}

function onUploadDrop(event: DragEvent) {
  if (isUploading.value) return;
  const files = Array.from(event.dataTransfer?.files ?? []);
  if (files.length) {
    selectedUploadFiles.value = mergeFiles(selectedUploadFiles.value, files);
  }
}

function relativePathForFile(file: File) {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
}

function mergeFiles(current: File[], incoming: File[]) {
  const next = [...current];
  for (const file of incoming) {
    const relativePath = relativePathForFile(file);
    const existingIndex = next.findIndex((item) => relativePathForFile(item) === relativePath);
    if (existingIndex >= 0) {
      next[existingIndex] = file;
    } else {
      next.push(file);
    }
  }
  return next;
}

function removeUploadFile(index: number) {
  if (isUploading.value) return;
  const next = selectedUploadFiles.value.filter((_, itemIndex) => itemIndex !== index);
  selectedUploadFiles.value = next;
}

function clearUploadFiles() {
  if (isUploading.value) return;
  selectedUploadFiles.value = [];
}

async function checkBulkUpload() {
  if (!canCheckUpload.value) return;
  if (!validateUploadForm()) return;
  isCheckingUpload.value = true;
  try {
    uploadCheckResult.value = await checkBulkFileUpload({
      targetIds: [...selectedTargetIds.value],
      remoteDirectory: remoteDirectory.value.trim() || '/tmp/',
      filenames: selectedUploadFiles.value.map(relativePathForFile),
      totalSize: uploadTotalSize.value,
    });
    overwriteConfirmed.value = !uploadHasWarnings.value;
    if (!uploadCheckResult.value.usableTargetIds.length) showToast('没有可上传主机', '所选主机当前都无法连接。', 'error');
  } catch (error) {
    uploadCheckResult.value = null;
    showToast('上传检查失败', errorMessage(error), 'error');
  } finally {
    isCheckingUpload.value = false;
  }
}

async function submitUploadFlow() {
  if (!canCreateUpload.value) return;
  if (!validateUploadForm()) return;
  if (!uploadCheckResult.value) {
    await checkBulkUpload();
    return;
  }
  await createUploadTask();
}

async function createUploadTask() {
  if (!canCreateUpload.value) return;
  if (!validateUploadForm()) return;
  if (!uploadCheckResult.value) {
    await checkBulkUpload();
    return;
  }
  if (!usableUploadTargetIds.value.length) {
    showToast('没有可上传主机', '所选主机当前都无法连接。', 'error');
    return;
  }
  if (uploadHasWarnings.value && !overwriteConfirmed.value) {
    showToast('需要确认覆盖', '请确认后再开始上传。', 'error');
    return;
  }
  isUploading.value = true;
  try {
    const task = await createBulkFileUploadTask({
      targetIds: usableUploadTargetIds.value,
      remoteDirectory: remoteDirectory.value.trim() || '/tmp/',
      files: selectedUploadFiles.value,
      relativePaths: selectedUploadFiles.value.map(relativePathForFile),
      overwrite: overwriteConfirmed.value,
      name: taskName.value.trim(),
    });
    taskName.value = '';
    selectedUploadFiles.value = [];
    remoteDirectory.value = '/tmp/';
    uploadCheckResult.value = null;
    overwriteConfirmed.value = false;
    scriptSourceName.value = '';
    selectedTargetIds.value = new Set();
    taskPage.value = 1;
    await loadTasks();
    await selectTask(task.id);
    showToast('文件上传已创建', '后台正在将文件分发到可连接主机。', 'success');
  } catch (error) {
    showToast('文件上传失败', errorMessage(error), 'error');
  } finally {
    isUploading.value = false;
  }
}

function setExecutionType(type: Exclude<BulkExecutionType, 'file_upload'>) {
  executionType.value = type;
  scriptSourceName.value = '';
}

function applyScriptPreset(preset: (typeof scriptPresets)[number]) {
  executionType.value = preset.type;
  commandInput.value = preset.command;
  scriptSourceName.value = '';
}

async function cancelSelectedTask() {
  if (!selectedTaskId.value || !canCancel.value || isControlBusy.value) return;
  isControlBusy.value = true;
  try {
    await cancelBulkExecutionTask(selectedTaskId.value);
    await Promise.all([loadTasks(), selectTask(selectedTaskId.value, false, false)]);
    showToast('已请求取消', '任务会在当前命令或文件传输结束后停止。', 'success');
  } catch (error) {
    showToast('取消任务失败', errorMessage(error), 'error');
  } finally {
    isControlBusy.value = false;
  }
}

function deleteSelectedTask() {
  if (!selectedTaskId.value || !canDelete.value) return;
  const taskId = selectedTaskId.value;
  const run = async () => {
    isControlBusy.value = true;
    try {
      await deleteBulkExecutionTask(taskId);
      selectedTaskId.value = null;
      selectedTask.value = null;
      isTaskDetailOpen.value = false;
      await loadTasks();
      showToast('任务已删除', '批量执行历史已移除。', 'success');
    } catch (error) {
      showToast('删除任务失败', errorMessage(error), 'error');
    } finally {
      isControlBusy.value = false;
    }
  };
  if (requestConfirm) requestConfirm('删除批量执行任务', '删除后会同时移除每台主机的执行结果。', '删除', run);
  else void run();
}

function deleteSelectedRecordTasks() {
  const taskIds = [...selectedRecordTaskIds.value];
  if (!taskIds.length || !canDelete.value || isControlBusy.value) return;
  const run = async () => {
    isControlBusy.value = true;
    try {
      await Promise.all(taskIds.map((taskId) => deleteBulkExecutionTask(taskId)));
      if (selectedTaskId.value && taskIds.includes(selectedTaskId.value)) {
        selectedTaskId.value = null;
        selectedTask.value = null;
        isTaskDetailOpen.value = false;
        resetUploadDetailView();
      }
      selectedRecordTaskIds.value = new Set();
      await loadTasks();
      showToast('任务已删除', `已删除 ${taskIds.length} 个批量执行任务。`, 'success');
    } catch (error) {
      showToast('批量删除失败', errorMessage(error), 'error');
    } finally {
      isControlBusy.value = false;
    }
  };
  const message = `将删除选中的 ${taskIds.length} 个批量执行任务，同时移除每台主机的执行结果。`;
  if (requestConfirm) requestConfirm('删除所选执行记录', message, '删除所选', run);
  else void run();
}

function toggleResult(resultId: number) {
  const next = new Set(expandedResultIds.value);
  if (next.has(resultId)) next.delete(resultId);
  else next.add(resultId);
  expandedResultIds.value = next;
}

function isResultExpanded(resultId: number) {
  return expandedResultIds.value.has(resultId);
}

function toggleAllResults() {
  const ids = selectedTaskResultIds.value;
  if (!ids.length) return;
  if (allResultsExpanded.value) {
    const selectedIds = new Set(ids);
    expandedResultIds.value = new Set([...expandedResultIds.value].filter((id) => !selectedIds.has(id)));
    return;
  }
  expandedResultIds.value = new Set([...expandedResultIds.value, ...ids]);
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    if (!hasRunningTask.value) return;
    if (pollInFlight.value) return;
    const taskToRefresh = isTaskDetailOpen.value && isTaskRunning(selectedTask.value) && selectedTaskId.value ? selectedTaskId.value : null;
    pollInFlight.value = true;
    try {
      await loadTasks();
      if (taskToRefresh && isTaskDetailOpen.value) await selectTask(taskToRefresh, false, false);
    } finally {
      pollInFlight.value = false;
    }
  }, 5000);
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function statusLabel(status: BulkExecutionStatus | BulkExecutionResultStatus) {
  return statusLabels[status] ?? status;
}

function isTaskRunning(task: Pick<BulkExecutionTask, 'status'> | BulkExecutionTaskDetail | null | undefined) {
  return task?.status === 'queued' || task?.status === 'running';
}

function transferProgress(transfers: BulkTransferItem[]) {
  if (!transfers.length) return 0;
  const done = transfers.filter((transfer) => ['success', 'failed', 'skipped'].includes(transfer.status)).length;
  return Math.round((done / transfers.length) * 100);
}

function formatTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : '-';
}

function formatDuration(task: BulkExecutionTask) {
  if (!task.startedAt) return '-';
  const end = task.finishedAt ? new Date(task.finishedAt).getTime() : Date.now();
  const seconds = Math.max(1, Math.round((end - new Date(task.startedAt).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${rest}s`;
}

function taskHostSummary(task: BulkExecutionTask) {
  if (selectedTask.value?.id === task.id && selectedTask.value.results.length) {
    const first = selectedTask.value.results[0];
    return selectedTask.value.results.length > 1 ? `${first.hostName} 等 ${selectedTask.value.results.length} 台` : first.hostName;
  }
  return `${task.targetCount} 台主机`;
}

function taskExitSummary(task: BulkExecutionTask) {
  if (task.status === 'completed' && task.failedCount === 0) return '0';
  if (task.failedCount > 0) return `失败 ${task.failedCount}`;
  if (task.skippedCount > 0) return `跳过 ${task.skippedCount}`;
  return '-';
}

function taskResultSummary(task: BulkExecutionTask) {
  return `成功 ${task.successCount ?? 0} / 失败 ${task.failedCount ?? 0}`;
}

function formatFileSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<template>
  <section class="bulk-execution-page">
    <article v-if="canRefresh || canExecute" class="bulk-execution-shell">
      <header class="bulk-execution-head">
        <div>
          <h2>批量执行</h2>
          <p>面向已验证 Linux SSH 主机执行命令和文件分发任务。</p>
        </div>
        <el-button-group class="bulk-execution-actions">
          <el-button v-if="canRefresh || canExecute" :type="activeBulkView === 'history' ? 'primary' : 'default'" :class="{ active: activeBulkView === 'history' }" @click="switchBulkView('history')"><AppIcon name="rows" :size="16" />执行记录</el-button>
          <el-button v-if="canExecute" :type="activeBulkView === 'execute' ? 'primary' : 'default'" :class="{ active: activeBulkView === 'execute' }" @click="openCreateDialog"><AppIcon name="terminal" :size="16" />新建执行</el-button>
          <el-button v-if="canExecute" :type="activeBulkView === 'upload' ? 'primary' : 'default'" :class="{ active: activeBulkView === 'upload' }" @click="openUploadDialog"><AppIcon name="upload" :size="16" />批量上传</el-button>
          <el-button v-if="canRefresh" :loading="isLoading" @click="refreshAll"><AppIcon name="refresh" :size="16" />刷新</el-button>
        </el-button-group>
      </header>

      <section v-show="activeBulkView === 'history'" class="bulk-history-view">
        <section class="bulk-record-panel">
          <header class="bulk-record-toolbar">
            <div class="bulk-record-heading">
              <h3>执行列表</h3>
            </div>
            <div class="bulk-record-actions">
              <label class="bulk-keyword-filter">
                <el-input v-model="keyword" clearable placeholder="搜索任务或命令" @keyup.enter="applyHistoryFilters" />
              </label>
              <label class="bulk-host-filter">
                <el-select v-model="hostFilter" aria-label="目标主机" @change="applyHistoryFilters">
                  <el-option value="" label="全部主机" />
                  <el-option v-for="target in targets" :key="target.id" :value="target.id" :label="`${target.name} / ${target.privateIp}`" />
                </el-select>
              </label>
              <label class="bulk-status-filter">
                <el-select v-model="statusFilter" aria-label="执行状态" @change="setHistoryStatus(statusFilter)">
                  <el-option v-for="option in historyStatusOptions" :key="option.value || 'all'" :value="option.value" :label="option.label" />
                </el-select>
              </label>
              <el-button class="bulk-query-button" :loading="isLoading" @click="applyHistoryFilters"><AppIcon name="search" :size="15" />查询</el-button>
              <el-button v-if="canRefresh" :loading="isLoading" circle aria-label="刷新" @click="refreshAll"><AppIcon name="refresh" :size="15" /></el-button>
            </div>
          </header>

          <div class="bulk-record-table">
            <el-table :data="taskHistory" class="bulk-record-grid app-data-table" row-key="id" empty-text="暂无批量执行任务" @row-click="(row) => selectTask(row.id, true, false)">
              <el-table-column width="54" align="center">
                <template #header>
                  <el-checkbox
                    class="bulk-record-select-cell"
                    :model-value="allVisibleRecordsSelected"
                    :disabled="!visibleRecordTaskIds.length"
                    :indeterminate="someVisibleRecordsSelected && !allVisibleRecordsSelected"
                    @change="toggleAllVisibleRecordTasks"
                  />
                </template>
                <template #default="{ row }">
                  <el-checkbox class="bulk-record-select-cell" :model-value="selectedRecordTaskIds.has(row.id)" @click.stop @change="toggleRecordTaskSelection(row.id, $event)" />
                </template>
              </el-table-column>
              <el-table-column label="编号" width="80" align="center">
                <template #default="{ $index }">{{ taskPageStart + $index }}</template>
              </el-table-column>
              <el-table-column label="执行机器" min-width="150">
                <template #default="{ row }">{{ taskHostSummary(row) }}</template>
              </el-table-column>
              <el-table-column prop="command" label="执行命令" min-width="220" show-overflow-tooltip />
              <el-table-column label="状态" min-width="120" align="center">
                <template #default="{ row }">{{ taskResultSummary(row) }}</template>
              </el-table-column>
              <el-table-column label="退出码" width="110" align="center">
                <template #default="{ row }">{{ taskExitSummary(row) }}</template>
              </el-table-column>
              <el-table-column label="持续时间" width="120" align="center">
                <template #default="{ row }">{{ formatDuration(row) }}</template>
              </el-table-column>
              <el-table-column prop="createdBy" label="执行用户" min-width="120" />
              <el-table-column label="创建时间" min-width="170">
                <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
              </el-table-column>
              <el-table-column prop="name" label="描述" min-width="180" show-overflow-tooltip />
              <el-table-column label="操作" width="220" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" text @click.stop="openTaskDetail(row.id)">详情</el-button>
                  <el-button v-if="canExecute" size="small" text @click.stop="rerunTaskFromList(row.id)">再次执行</el-button>
                  <el-button v-if="canDelete" size="small" text type="danger" @click.stop="deleteTaskFromList(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <footer class="bulk-record-footer">
            <div class="host-pagination bulk-record-pagination" aria-label="执行列表分页">
              <div class="bulk-record-pagination-left">
                <AppPagination
                  :page="taskPage"
                  :page-size="taskPageSize"
                  :total="taskTotal"
                  @page-change="setTaskPage"
                  @page-size-change="setTaskPageSize"
                />
              </div>
              <div class="bulk-record-stats">{{ taskTotal }} 个任务 · {{ targets.length }} 台可执行主机</div>
            </div>
          </footer>
          <div v-if="selectedRecordTaskIds.size" class="host-bulk-action-bar bulk-record-bulk-action-bar" @click.stop>
            <div class="host-bulk-action-info">
              <span class="host-bulk-action-icon"><AppIcon name="info" :size="16" /></span>
              <div class="host-bulk-action-copy">
                <strong>批量操作</strong>
                <span class="host-bulk-action-count">已选择 {{ selectedRecordTaskIds.size }} 个任务</span>
              </div>
            </div>
            <div class="host-bulk-action-buttons">
              <el-button class="host-bulk-button host-bulk-button-cancel" :disabled="isControlBusy" @click="clearSelectedRecordTasks">取消所选</el-button>
              <el-button v-if="canDelete" class="host-bulk-button host-bulk-button-delete" type="danger" :disabled="isControlBusy" @click="deleteSelectedRecordTasks">
                <AppIcon name="trash" :size="14" />
                删除所选
              </el-button>
            </div>
          </div>
        </section>

      </section>

      <section v-show="activeBulkView === 'execute'" class="bulk-execute-view">
        <div class="bulk-create-workbench">
          <section class="bulk-script-composer">
            <el-button-group class="bulk-mode-tabs" role="tablist" aria-label="执行类型">
              <el-button :type="executionType === 'shell' ? 'primary' : 'default'" :class="{ active: executionType === 'shell' }" @click="setExecutionType('shell')">
                <AppIcon name="terminal" :size="15" />
                普通 Shell
              </el-button>
            </el-button-group>
            <label class="bulk-task-name-field">
              <span>任务名称<em class="required-marker">*</em></span>
              <el-input v-model="taskName" maxlength="180" placeholder="请输入任务名称" :disabled="isCreating" />
            </label>
            <div class="bulk-script-presets">
              <el-button v-for="preset in scriptPresets" :key="preset.key" @click="applyScriptPreset(preset)">
                {{ preset.label }}
              </el-button>
            </div>
            <div class="bulk-script-editor">
              <input ref="scriptFileInput" hidden type="file" :accept="scriptFileAccept" @change="onScriptFileChange" />
              <div class="bulk-script-editor-head">
                <span>{{ executionTypeLabels[executionType] }}<em class="required-marker">*</em></span>
                <div class="bulk-script-editor-actions">
                  <el-button class="bulk-script-upload-button" :disabled="isCreating" @click="triggerScriptFileSelect">
                    <AppIcon name="upload" :size="14" />
                    {{ scriptUploadButtonLabel }}
                  </el-button>
                  <el-button
                    class="bulk-script-clear-button"
                    :disabled="isCreating || !canClearScriptInput"
                    aria-label="清空脚本内容"
                    title="清空脚本内容"
                    @click="clearScriptInput"
                  >
                    <AppIcon name="reset" :size="14" />
                  </el-button>
                </div>
              </div>
              <div v-if="scriptSourceName" class="bulk-script-source">
                <AppIcon name="file" :size="14" />
                <span>{{ scriptSourceName }}</span>
              </div>
              <el-input v-model="commandInput" class="commandInput" type="textarea" :rows="16" :maxlength="MAX_SCRIPT_LENGTH" :placeholder="commandPlaceholder" :disabled="isCreating" />
            </div>
          </section>

          <section class="bulk-target-summary">
            <header>
              <div>
                <h3>目标机器<em class="required-marker">*</em></h3>
                <span>已选 {{ selectedTargets.length }} / {{ targets.length }}</span>
              </div>
              <el-button :loading="isTargetsLoading" @click="openTargetPicker"><AppIcon name="server" :size="15" />选择机器</el-button>
            </header>
            <div v-if="!selectedTargets.length" class="bulk-target-empty">
              <AppIcon name="server" :size="28" />
              <strong>尚未选择机器</strong>
              <span>{{ isTargetsLoading ? '目标加载中...' : '点击选择机器添加执行目标' }}</span>
            </div>
            <div v-else class="bulk-selected-target-list">
              <div v-for="target in selectedTargets" :key="target.id" class="bulk-selected-target-row">
                <div class="bulk-selected-target-main">
                  <strong class="bulk-selected-target-name">{{ target.name }}</strong>
                  <span class="bulk-selected-target-meta">
                    <span class="bulk-selected-target-ip">{{ target.privateIp || '-' }}</span>
                    <span class="bulk-selected-target-user">{{ target.loginUser || '-' }}</span>
                    <span class="bulk-selected-target-group">{{ target.groupName || '-' }}</span>
                  </span>
                </div>
                <el-button class="bulk-selected-target-remove" circle aria-label="移除目标机器" :disabled="isCreating" @click="removeSelectedTarget(target.id)">
                  <AppIcon name="x" :size="14" />
                </el-button>
              </div>
              <el-button class="bulk-clear-targets" :disabled="isCreating" @click="clearSelectedTargets">清空选择</el-button>
            </div>
          </section>
        </div>
        <footer class="bulk-workbench-footer">
          <el-button :disabled="isCreating" @click="switchBulkView('history')">返回记录</el-button>
          <el-button type="primary" :disabled="!canCreateTask" :loading="isCreating" @click="createTaskWithConfirmation">{{ isCreating ? '创建中...' : executeActionLabel }}</el-button>
        </footer>
      </section>

      <section v-show="activeBulkView === 'upload'" class="bulk-upload-view">
        <div class="bulk-create-workbench">
          <section class="bulk-script-composer bulk-upload-composer">
            <label class="bulk-task-name-field">
              <span>任务名称<em class="required-marker">*</em></span>
              <el-input v-model="taskName" maxlength="180" placeholder="请输入任务名称" :disabled="isUploading" />
            </label>
            <input ref="uploadFileInput" hidden type="file" multiple @change="onUploadFileChange" />
            <input ref="uploadFolderInput" hidden type="file" webkitdirectory directory multiple @change="onUploadFolderChange" />
            <div
              class="bulk-upload-dropzone"
              @dragover.prevent
              @drop.prevent="onUploadDrop"
            >
              <AppIcon name="upload" :size="38" />
              <strong>{{ selectedUploadFiles.length ? `${selectedUploadFiles.length} 个文件` : '选择文件或文件夹' }}<em class="required-marker">*</em></strong>
              <span>{{ selectedUploadFiles.length ? formatFileSize(uploadTotalSize) : '支持多文件和文件夹上传，并保留本地目录层级' }}</span>
              <div class="bulk-upload-select-actions">
                <el-button :disabled="isUploading" @click="triggerUploadFileSelect">
                  <AppIcon name="file" :size="14" />
                  选择文件
                </el-button>
                <el-button :disabled="isUploading" @click="triggerUploadFolderSelect">
                  <AppIcon name="folder" :size="14" />
                  选择文件夹
                </el-button>
              </div>
            </div>
            <div v-if="selectedUploadFiles.length" class="bulk-upload-file-stack">
              <div class="bulk-upload-file-summary">
                <span>{{ selectedUploadFiles.length }} 个文件 · {{ formatFileSize(uploadTotalSize) }}</span>
                <el-button class="bulk-upload-clear-files" :disabled="isUploading" @click="clearUploadFiles">清空文件</el-button>
              </div>
              <div class="bulk-upload-file-list-scroll">
                <div v-for="(file, index) in selectedUploadFiles" :key="`${relativePathForFile(file)}-${file.size}-${file.lastModified}`" class="bulk-upload-file-row">
                  <span class="bulk-upload-file-name" :title="relativePathForFile(file)">{{ relativePathForFile(file) }}</span>
                  <em>{{ formatFileSize(file.size) }}</em>
                  <el-button circle :disabled="isUploading" @click="removeUploadFile(index)"><AppIcon name="x" :size="14" /></el-button>
                </div>
              </div>
            </div>

            <label class="bulk-upload-path">
              <span>远程目录<em class="required-marker">*</em></span>
              <el-input v-model="remoteDirectory" :disabled="isUploading" placeholder="/tmp/" />
            </label>
            <p class="bulk-upload-hint">上传前会检查主机连接和同名文件；确认后将覆盖已存在的同名文件。</p>

            <section v-if="uploadCheckResult" class="bulk-upload-check-panel">
              <header>
                <strong>上传检查</strong>
                <span>{{ uploadCheckResult.connectedTargets.length }} 台可连接 · {{ unreachableTargets.length }} 台不可连接</span>
              </header>
              <div v-if="unreachableTargets.length" class="bulk-upload-warning">
                <strong>不可连接主机</strong>
                <span v-for="target in unreachableTargets" :key="target.id">{{ target.name }} / {{ target.privateIp }} · {{ target.error }}</span>
              </div>
              <div v-if="duplicateFiles.length" class="bulk-upload-warning">
                <strong>重复文件</strong>
                <span v-for="item in duplicateFiles" :key="item.targetId">{{ item.hostName }} / {{ item.hostIp }} · {{ item.filenames.join(', ') }}</span>
              </div>
              <el-checkbox v-if="uploadHasWarnings" v-model="overwriteConfirmed" class="bulk-upload-overwrite">
                确认继续上传，并覆盖重复文件
              </el-checkbox>
            </section>
          </section>

          <section class="bulk-target-summary">
            <header>
              <div>
                <h3>目标机器<em class="required-marker">*</em></h3>
                <span>已选 {{ selectedTargets.length }} / {{ targets.length }}</span>
              </div>
              <el-button :loading="isTargetsLoading" :disabled="isUploading" @click="openTargetPicker"><AppIcon name="server" :size="15" />选择机器</el-button>
            </header>
            <div v-if="!selectedTargets.length" class="bulk-target-empty">
              <AppIcon name="server" :size="28" />
              <strong>尚未选择机器</strong>
              <span>{{ isTargetsLoading ? '目标加载中...' : '点击选择机器添加上传目标' }}</span>
            </div>
            <div v-else class="bulk-selected-target-list">
              <div v-for="target in selectedTargets" :key="target.id" class="bulk-selected-target-row">
                <div class="bulk-selected-target-main">
                  <strong class="bulk-selected-target-name">{{ target.name }}</strong>
                  <span class="bulk-selected-target-meta">
                    <span class="bulk-selected-target-ip">{{ target.privateIp || '-' }}</span>
                    <span class="bulk-selected-target-user">{{ target.loginUser || '-' }}</span>
                    <span class="bulk-selected-target-group">{{ target.groupName || '-' }}</span>
                  </span>
                </div>
                <el-button class="bulk-selected-target-remove" circle aria-label="移除目标机器" :disabled="isUploading || isCheckingUpload" @click="removeSelectedTarget(target.id)">
                  <AppIcon name="x" :size="14" />
                </el-button>
              </div>
              <el-button class="bulk-clear-targets" :disabled="isUploading || isCheckingUpload" @click="clearSelectedTargets">清空选择</el-button>
            </div>
          </section>
        </div>
        <footer class="bulk-workbench-footer">
          <el-button :disabled="isCheckingUpload || isUploading" @click="switchBulkView('history')">返回记录</el-button>
          <el-button :disabled="!canCheckUpload" :loading="isCheckingUpload" @click="checkBulkUpload">{{ isCheckingUpload ? '检查中...' : '检查文件' }}</el-button>
          <el-button type="primary" :disabled="!canCreateUpload || (uploadHasWarnings && !overwriteConfirmed)" :loading="isUploading" @click="submitUploadFlow">
            {{ isUploading ? '上传中...' : '开始上传' }}
          </el-button>
        </footer>
      </section>

      <el-dialog v-model="isTargetPickerOpen" class="bulk-target-picker-modal" title="选择机器" width="920px" :close-on-click-modal="false" @close="closeTargetPicker">
          <header class="bulk-target-picker-title">
            <div>
              <h3>选择机器</h3>
              <p>已选 {{ draftTargetIds.size }} / {{ targets.length }}</p>
            </div>
          </header>
          <div class="bulk-target-picker-body popup-body">
            <aside class="bulk-target-group-tree" aria-label="目标分组树">
              <el-button class="bulk-target-group-row bulk-target-group-root" :class="{ active: targetGroupFilter === null }" text @click="selectTargetGroup(null)">
                <span class="folder-caret"><AppIcon name="chevronDown" :size="15" /></span>
                <span class="folder-icon"><AppIcon name="folder" :size="16" /></span>
                <strong>全部分组</strong>
                <em>{{ targets.length }}</em>
              </el-button>
              <el-button
                v-for="row in targetGroupRows"
                :key="row.group.key"
                class="bulk-target-group-row"
                :class="{ active: targetGroupFilter === row.group.key }"
                :style="{ paddingLeft: `${10 + row.level * 10}px` }"
                text
                @click="selectTargetGroup(row.group.key)"
              >
                <span class="folder-caret" :class="{ expandable: row.hasChildren }" @click.stop="row.hasChildren && toggleTargetGroupCollapsed(row.group.key)">
                  <AppIcon v-if="row.hasChildren" :name="row.expanded ? 'chevronDown' : 'chevronRight'" :size="15" />
                </span>
                <span class="folder-icon"><AppIcon name="folder" :size="16" /></span>
                <strong>{{ row.group.label }}</strong>
                <em>{{ row.group.count }}</em>
              </el-button>
              <div v-if="!targetGroupRows.length" class="bulk-empty">{{ isTargetsLoading ? '加载中...' : '暂无可执行分组' }}</div>
            </aside>
            <section class="bulk-target-picker-list-panel">
              <header>
                <el-input v-model="targetPickerKeyword" clearable placeholder="搜索主机 / IP / 分组" />
                <el-tag type="info" effect="plain">已选 {{ draftSelectedTargets.length }} / {{ targets.length }}</el-tag>
              </header>
              <div class="bulk-target-picker-list">
                <div class="bulk-target-picker-row head">
                  <el-checkbox class="bulk-target-picker-check" :model-value="allPickerTargetsSelected" :disabled="!pickerTargets.length" @change="toggleAllPickerTargetsFromEvent" />
                  <span>主机</span>
                  <span>IP地址</span>
                  <span>用户</span>
                  <span>分组</span>
                </div>
                <label v-for="target in pickerTargets" :key="target.id" class="bulk-target-picker-row">
                  <el-checkbox :model-value="draftTargetIds.has(target.id)" @change="toggleDraftTargetFromEvent(target.id, $event)" />
                  <strong :title="target.name">{{ target.name }}</strong>
                  <span :title="target.privateIp || '-'">{{ target.privateIp || '-' }}</span>
                  <span :title="target.loginUser || '-'">{{ target.loginUser || '-' }}</span>
                  <span :title="target.groupName || '-'">{{ target.groupName || '-' }}</span>
                </label>
                <div v-if="!pickerTargets.length" class="bulk-empty">{{ isTargetsLoading ? '加载中...' : '暂无匹配的可执行 Linux SSH 主机' }}</div>
              </div>
            </section>
          </div>
          <template #footer>
            <div class="popup-footer popup-actions">
              <el-button @click="closeTargetPicker">取消</el-button>
              <el-button type="primary" @click="confirmTargetSelection">确定选择</el-button>
            </div>
          </template>
      </el-dialog>

      <el-dialog
        v-model="isTaskDetailOpen"
        class="bulk-task-detail-modal"
        title="执行详情"
        width="min(1440px, calc(100vw - 48px))"
        top="24px"
        append-to-body
        destroy-on-close
        :close-on-click-modal="false"
        @close="closeTaskDetail"
      >
        <div class="bulk-task-detail">
          <template v-if="selectedTask">
            <header>
              <div>
                <h3>{{ selectedTask.name }}</h3>
                <p>{{ selectedTask.createdBy }} · {{ selectedTaskExecutionType }} · {{ statusLabel(selectedTask.status) }} · {{ selectedTaskProgress }}%</p>
              </div>
              <div>
                <el-button :disabled="!selectedTask.results.length" @click="toggleAllResults">{{ allResultsExpanded ? '全部收起' : '全部展开' }}</el-button>
                <el-button v-if="canCancel" :disabled="!selectedTaskCanCancel || isControlBusy" @click="cancelSelectedTask">取消</el-button>
                <el-button v-if="canDelete" type="danger" plain :disabled="isControlBusy" @click="deleteSelectedTask"><AppIcon name="trash" :size="15" />删除</el-button>
              </div>
            </header>
            <pre class="bulk-command-block">{{ selectedTask.command }}</pre>
            <div v-if="selectedTask.executionType === 'file_upload'" class="bulk-upload-detail-switch">
              <el-button :type="uploadDetailView === 'hosts' ? 'primary' : 'default'" :class="{ active: uploadDetailView === 'hosts' }" @click="setUploadDetailView('hosts')">
                <AppIcon name="server" :size="14" />
                主机列表
              </el-button>
              <el-button :type="uploadDetailView === 'files' ? 'primary' : 'default'" :class="{ active: uploadDetailView === 'files' }" @click="setUploadDetailView('files')">
                <AppIcon name="folder" :size="14" />
                上传文件
              </el-button>
              <el-button :type="uploadDetailView === 'directory' ? 'primary' : 'default'" :class="{ active: uploadDetailView === 'directory' }" @click="setUploadDetailView('directory')">
                <AppIcon name="terminal" :size="14" />
                远程目录
              </el-button>
              <el-tag class="bulk-upload-detail-size" type="info" effect="plain">大小 {{ formatFileSize(selectedTaskUploadSize) }}</el-tag>
            </div>
            <el-alert v-if="selectedTask.error" class="bulk-error" type="error" :closable="false" :title="selectedTask.error" />
            <el-progress :percentage="selectedTaskProgress" :stroke-width="10" />

            <div v-if="selectedTask.executionType === 'file_upload' && uploadDetailView === 'files'" class="bulk-upload-detail-tree">
              <el-button
                v-for="row in uploadFileTreeRows"
                :key="row.key"
                class="bulk-upload-tree-row"
                :class="{ 'is-folder': row.type === 'directory', 'is-file': row.type === 'file', 'is-expanded': row.expanded }"
                :disabled="row.type !== 'directory'"
                @click="toggleUploadFolder(row)"
              >
                <span class="bulk-upload-tree-indent" :style="{ width: `${row.level * 18}px` }"></span>
                <span class="bulk-upload-tree-toggle">
                  <AppIcon v-if="row.type === 'directory'" :name="row.expanded ? 'chevronDown' : 'chevronRight'" :size="14" />
                </span>
                <AppIcon :name="row.type === 'directory' ? (row.expanded ? 'folderOpen' : 'folder') : 'file'" :size="14" />
                <strong :title="row.file?.filename || row.name">{{ row.name }}</strong>
                <em>{{ row.type === 'file' ? formatFileSize(row.size) : '文件夹' }}</em>
              </el-button>
              <el-empty v-if="!uploadFileTreeRows.length" class="bulk-empty" description="暂无上传文件" />
            </div>

            <div v-else-if="selectedTask.executionType === 'file_upload' && uploadDetailView === 'directory'" class="bulk-upload-detail-directory">
              <strong>远程目录</strong>
              <code>{{ selectedTask.remoteDirectory || '-' }}</code>
            </div>

            <div v-else class="bulk-result-table">
              <div class="bulk-result-row head">
                <span>主机</span>
                <span>IP</span>
                <span>用户</span>
                <span>状态</span>
                <span>退出码</span>
                <span>进度</span>
                <span>输出</span>
              </div>
              <template v-for="result in selectedTask.results" :key="result.id">
                <div class="bulk-result-row">
                  <strong>{{ result.hostName }}</strong>
                  <span>{{ result.hostIp }}:{{ result.hostPort }}</span>
                  <span>{{ result.loginUser || '-' }}</span>
                  <el-tag class="bulk-status" :class="`status-${result.status}`" effect="plain">{{ statusLabel(result.status) }}</el-tag>
                  <span>{{ result.exitCode ?? '-' }}</span>
                  <span>{{ result.transfers?.length ? `${transferProgress(result.transfers)}%` : formatTime(result.finishedAt || result.startedAt) }}</span>
                  <el-button circle @click="toggleResult(result.id)">
                    <AppIcon :name="isResultExpanded(result.id) ? 'chevronDown' : 'chevronRight'" :size="15" />
                  </el-button>
                </div>
                <div v-if="isResultExpanded(result.id)" class="bulk-result-output">
                  <div v-if="result.transfers?.length" class="bulk-transfer-matrix">
                    <div v-for="transfer in result.transfers" :key="transfer.id" class="bulk-transfer-row">
                      <strong>{{ transfer.remotePath }}</strong>
                      <el-tag class="bulk-status" :class="`status-${transfer.status}`" effect="plain">{{ statusLabel(transfer.status) }}</el-tag>
                      <span>{{ formatFileSize(transfer.size) }}</span>
                      <em>{{ transfer.error || '-' }}</em>
                    </div>
                  </div>
                  <div>
                    <strong>stdout</strong>
                    <pre>{{ result.stdout || '无标准输出' }}</pre>
                  </div>
                  <div>
                    <strong>stderr</strong>
                    <pre>{{ result.stderr || result.error || '无错误输出' }}</pre>
                  </div>
                  <span v-if="result.outputTruncated">输出已截断</span>
                </div>
              </template>
            </div>
          </template>
          <el-empty v-else class="bulk-empty" description="请选择一个任务查看结果" />
        </div>
      </el-dialog>
    </article>
    <div v-else class="permission-empty">暂无可用功能</div>
  </section>
</template>
