<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui';
import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { useAppContext } from '@app/context';
import { useColumnVisibility } from '@shared/composables/useColumnVisibility';
import {
  createQuickCommand,
  deleteQuickCommand,
  listQuickCommands,
  reorderQuickCommands,
  updateQuickCommand,
  type QuickCommand,
  type QuickCommandPayload,
} from '../../../services/quickCommands';
import { formatDateTime } from '../../../utils/datetime';
import AppIcon from '@shared/components/AppIcon.vue';
import HostEditorDialog from './HostEditorDialog.vue';
import HostGroupTree from './HostGroupTree.vue';
import HostMoveDialog from './HostMoveDialog.vue';
import HostTable from './HostTable.vue';
import type { HostMoveForm, ManagedHostForm } from '../composables/useHostEditor';
import HostToolbar, { type HostColumnKey } from './HostToolbar.vue';

interface HostQuickCommandDialogState {
  visible: boolean;
  mode: 'create' | 'edit';
  commandId: number | null;
  draft: QuickCommandPayload;
  saving: boolean;
  error: string;
}

const hostColumnOptions = [
  { key: 'group', label: '主机分组', width: 'minmax(84px, 0.7fr)', minWidth: 84 },
  { key: 'name', label: '节点', width: 'minmax(102px, 0.85fr)', minWidth: 102 },
  { key: 'ip', label: 'IP地址', width: 'minmax(126px, 0.95fr)', minWidth: 126 },
  { key: 'machine', label: '机器名称', width: 'minmax(92px, 0.7fr)', minWidth: 92 },
  { key: 'spec', label: '主机规格', width: 'minmax(150px, 1fr)', minWidth: 150 },
  { key: 'platformType', label: '平台类型', width: 'minmax(76px, 0.52fr)', minWidth: 76 },
  { key: 'user', label: '用户', width: 'minmax(68px, 0.55fr)', minWidth: 68 },
  { key: 'port', label: '端口', width: 'minmax(56px, 0.38fr)', minWidth: 56 },
  { key: 'createdAt', label: '创建时间', width: 'minmax(126px, 0.85fr)', minWidth: 126 },
  { key: 'updatedAt', label: '更新时间', width: 'minmax(126px, 0.85fr)', minWidth: 126 },
  { key: 'creator', label: '创建者', width: 'minmax(76px, 0.55fr)', minWidth: 76 },
  { key: 'remark', label: '备注', width: 'minmax(104px, 0.82fr)', minWidth: 104 },
  { key: 'collect', label: '采集', width: 'minmax(74px, 0.48fr)', minWidth: 74 },
  { key: 'status', label: '状态', width: 'minmax(86px, 0.65fr)', minWidth: 86 },
  { key: 'actions', label: '操作', width: 'minmax(132px, 0.8fr)', minWidth: 132 },
] as const;

const defaultVisibleHostColumnKeys = [
  'group',
  'name',
  'ip',
  'machine',
  'spec',
  'platformType',
  'remark',
  'collect',
  'status',
  'actions',
] as const satisfies readonly HostColumnKey[];
const bulkExecutionDraftTargetIdsKey = 'ops-tool.bulk-execution.draft-target-ids';
const bulkExecutionUploadTargetIdsKey = 'ops-tool.bulk-execution.upload-target-ids';
const fallbackHostColumnKey: HostColumnKey = 'name';

const {
  activeTool,
  hostGroups,
  hostGroupRoot,
  flatHostGroups,
  hostGroupRows,
  hostGroupRootExpanded,
  selectedHostGroup,
  selectManagedGroup,
  isHostGroupExpanded,
  toggleHostGroupExpanded,
  openHostGroupMenu,
  closeHostGroupMenu,
  hostSearch,
  hostStatusFilter,
  hostSortKey,
  hostSortDirection,
  hostCredentials,
  managedHostStats,
  managedHosts,
  visibleManagedHosts,
  groupMoveHosts,
  isLoadingHosts,
  hostGroupInlineEdit,
  rootHostGroupDialogOpen,
  rootHostGroupName,
  rootHostGroupSortAfter,
  hostGroupMenu,
  hostDialog,
  hostForm,
  hostFormErrors,
  hostMoveDialogOpen,
  hostMoveMode,
  hostMoveForm,
  draggedHostGroupId,
  hostGroupDropTarget,
  verifyingHostIds,
  selectedManagedHostIds,
  loadHostManagement,
  openHostTransferDialog,
  setHostSort,
  hostSortMark,
  hostGroupName,
  openAddRootHostGroup,
  openAddHostGroup,
  openRenameHostGroup,
  toggleHostGroupRootExpanded,
  startHostGroupDrag,
  updateHostGroupDropTarget,
  clearHostGroupDropTarget,
  dropHostGroup,
  finishHostGroupDrag,
  saveHostGroupInlineEdit,
  saveRootHostGroup,
  cancelHostGroupInlineEdit,
  openWebTerminal,
  openSimpleHostTerminal,
  addManagedHost,
  verifyManagedHost,
  verifyVisibleManagedHosts,
  verifySelectedManagedHosts,
  editManagedHost,
  saveManagedHost,
  applyCredentialToHostForm,
  uploadHostPrivateKey,
  openMoveHostDialog,
  openMoveSelectedHostsDialog,
  saveMoveManagedHost,
  deleteManagedHost,
  deleteSelectedManagedHosts,
  deleteManagedHostsInGroup,
  deleteHostGroup,
  setActiveTool,
  canUsePageAction,
  canUseAnyPageAction,
  showToast,
} = useAppContext();

const hostColumnSettingsOpen = ref(false);
const hostMoreActionsOpen = ref(false);
const fullscreen = ref(false);
const hostPage = ref(1);
const hostPageSize = ref(10);
const hostColumnWidths = ref<Partial<Record<HostColumnKey, number>>>({});
let stopHostColumnResize: (() => void) | null = null;
const hostQuickCommandManagerOpen = ref(false);
const hostQuickCommands = ref<QuickCommand[]>([]);
const hostQuickCommandCategory = ref('all');
const hostQuickCommandSearch = ref('');
const isHostQuickCommandLoading = ref(false);
const hostQuickCommandError = ref('');
const hostQuickCommandDialog = ref<HostQuickCommandDialogState>({
  visible: false,
  mode: 'create',
  commandId: null,
  draft: createHostQuickCommandDraft(),
  saving: false,
  error: '',
});
const canUseHostList = computed(() =>
  canUsePageAction('hosts', 'create') ||
  canUsePageAction('hosts', 'edit') ||
  canUsePageAction('hosts', 'delete') ||
  canUsePageAction('hosts', 'verify') ||
  canUsePageAction('hosts', 'move') ||
  canUsePageAction('hosts', 'filter') ||
  canUsePageAction('hosts', 'group') ||
  canUsePageAction('hosts', 'import') ||
  canUsePageAction('hosts', 'export') ||
  canUsePageAction('hosts', 'terminal') ||
  canUsePageAction('hosts', 'quick_commands') ||
  canUsePageAction('bulkExecution', 'execute')
);
const {
  visibility: hostColumnVisibility,
  visibleColumns: visibleHostTableColumns,
  allColumnsVisible: allHostColumnsVisible,
  someColumnsVisible: someHostColumnsVisible,
  isColumnVisible: isHostColumnVisible,
  isOnlyVisibleColumn: isOnlyVisibleHostColumn,
  updateColumnVisibility: updateHostColumnVisibility,
  toggleAllColumns: toggleAllHostColumns,
  resetColumns: resetHostColumns,
} = useColumnVisibility(hostColumnOptions, {
  fallbackKey: fallbackHostColumnKey,
  defaultVisibleKeys: defaultVisibleHostColumnKeys,
});
const hostTableStyle = computed<Record<string, string>>(() => {
  const columns = visibleHostTableColumns.value;
  const selectColumnWidth = 32;
  const minimumWidth = columns.reduce((total, column) => {
    const width = hostColumnWidths.value[column.key];
    return total + (width ?? column.minWidth ?? 0);
  }, 0)
    + selectColumnWidth;
  const actionsVisible = columns.some((column) => column.key === 'actions');
  const templateColumns = columns.map((column) => {
    if (column.key === 'status') return 'var(--host-status-column-width)';
    if (column.key === 'actions') return 'var(--host-actions-column-width)';
    const width = hostColumnWidths.value[column.key];
    if (width) return `${width}px`;
    return column.width;
  });

  return {
    '--host-table-columns': `var(--host-select-column-width) ${templateColumns.join(' ') || 'minmax(180px, 1fr)'}`,
    '--host-table-min-width': `${Math.max(760, minimumWidth)}px`,
    '--host-select-column-width': '32px',
    '--host-status-column-width': '86px',
    '--host-actions-column-width': '132px',
    '--host-status-sticky-right': actionsVisible ? 'var(--host-actions-column-width)' : '0px',
  };
});
const hostTotalPages = computed(() => Math.max(1, Math.ceil(visibleManagedHosts.value.length / hostPageSize.value)));
const paginatedManagedHosts = computed(() => {
  const start = (hostPage.value - 1) * hostPageSize.value;
  return visibleManagedHosts.value.slice(start, start + hostPageSize.value);
});
const visibleHostIds = computed(() => paginatedManagedHosts.value.map((host) => host.id));
const allVisibleHostsSelected = computed(() => visibleHostIds.value.length > 0 && visibleHostIds.value.every((id) => selectedManagedHostIds.value.has(id)));
const someVisibleHostsSelected = computed(() => visibleHostIds.value.some((id) => selectedManagedHostIds.value.has(id)));
const selectedManagedHostCount = computed(() => selectedManagedHostIds.value.size);
const canUseHostAnyAction = computed(() => canUseHostList.value);
const canUseHostMoreActions = computed(() =>
  canUsePageAction('hosts', 'verify') ||
  canUsePageAction('bulkExecution', 'execute') ||
  canUsePageAction('hosts', 'filter') ||
  canUsePageAction('hosts', 'move') ||
  canUsePageAction('hosts', 'delete')
);
const canUseHostRowActions = computed(() =>
  canUsePageAction('hosts', 'edit') ||
  canUsePageAction('hosts', 'verify') ||
  canUsePageAction('hosts', 'terminal') ||
  canUsePageAction('hosts', 'delete')
);
const selectedManagedHostVerifyingCount = computed(() =>
  [...selectedManagedHostIds.value].filter((hostId) => verifyingHostIds.value.has(hostId)).length,
);
const hostQuickCommandCategories = computed(() => {
  const categories = hostQuickCommands.value.map((command) => command.category).filter(Boolean);
  return [...new Set(categories)].sort((left, right) => left.localeCompare(right, 'zh-Hans-CN'));
});
const filteredHostQuickCommands = computed(() => {
  const query = hostQuickCommandSearch.value.trim().toLowerCase();
  return hostQuickCommands.value.filter((command) => {
    const matchesCategory = hostQuickCommandCategory.value === 'all' || command.category === hostQuickCommandCategory.value;
    if (!matchesCategory) return false;
    if (!query) return true;
    return [command.name, command.category, command.command, command.description]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
});

watch([visibleManagedHosts, hostPageSize], () => {
  if (hostPage.value > hostTotalPages.value) {
    hostPage.value = hostTotalPages.value;
  }
});

watch([hostSearch, selectedHostGroup, hostStatusFilter, hostSortKey, hostSortDirection], () => {
  hostPage.value = 1;
});

function updateHostMoveFormField(field: keyof HostMoveForm, value: number | null) {
  hostMoveForm.value[field] = value;
}

function updateHostFormField<Key extends keyof ManagedHostForm>(field: Key, value: ManagedHostForm[Key]) {
  (hostForm.value as ManagedHostForm)[field] = value;
}

function updateHostGroupInlineName(value: string) {
  if (hostGroupInlineEdit.value) hostGroupInlineEdit.value.name = value;
}

function checkedFromControl(value: Event | boolean | string | number) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return value === 'true';
  if (typeof value === 'number') return value !== 0;
  return (value.target as HTMLInputElement).checked;
}

function toggleAllVisibleHosts(value: Event | boolean | string | number) {
  const checked = checkedFromControl(value);
  const next = new Set(selectedManagedHostIds.value);
  visibleHostIds.value.forEach((id) => {
    if (checked) {
      next.add(id);
    } else {
      next.delete(id);
    }
  });
  selectedManagedHostIds.value = next;
}

function toggleHostSelected(hostId: number, value: Event | boolean | string | number) {
  const checked = checkedFromControl(value);
  const next = new Set(selectedManagedHostIds.value);
  if (checked) {
    next.add(hostId);
  } else {
    next.delete(hostId);
  }
  selectedManagedHostIds.value = next;
}

function clearSelectedManagedHosts() {
  selectedManagedHostIds.value = new Set();
}

function setHostPage(page: number) {
  hostPage.value = Math.min(Math.max(1, page), hostTotalPages.value);
}

function closeHostMenus() {
  closeHostGroupMenu();
  closeHostColumnSettings();
  closeHostMoreActions();
}

function toggleHostColumnSettings() {
  closeHostGroupMenu();
  closeHostMoreActions();
  hostColumnSettingsOpen.value = !hostColumnSettingsOpen.value;
}

function closeHostColumnSettings() {
  hostColumnSettingsOpen.value = false;
}

function toggleHostMoreActions() {
  closeHostGroupMenu();
  closeHostColumnSettings();
  hostMoreActionsOpen.value = !hostMoreActionsOpen.value;
}

function closeHostMoreActions() {
  hostMoreActionsOpen.value = false;
}

function resizeHostColumn(key: HostColumnKey, width: number) {
  const column = hostColumnOptions.find((option) => option.key === key);
  if (!column || key === 'status' || key === 'actions') return;
  hostColumnWidths.value = {
    ...hostColumnWidths.value,
    [key]: Math.max(column.minWidth, Math.round(width)),
  };
}

function startHostColumnResize(key: HostColumnKey, event: MouseEvent) {
  if (key === 'status' || key === 'actions') return;
  event.preventDefault();
  stopHostColumnResize?.();
  const startX = event.clientX;
  const headerCell = (event.currentTarget as HTMLElement).closest('.host-table-head-cell');
  const startWidth = headerCell?.getBoundingClientRect().width ?? hostColumnOptions.find((column) => column.key === key)?.minWidth ?? 80;

  const onMove = (moveEvent: MouseEvent) => {
    resizeHostColumn(key, startWidth + moveEvent.clientX - startX);
  };
  const onEnd = () => {
    stopHostColumnResize?.();
    stopHostColumnResize = null;
  };
  stopHostColumnResize = () => {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onEnd);
    document.body.classList.remove('host-column-resizing');
  };

  document.body.classList.add('host-column-resizing');
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onEnd, { once: true });
}

onBeforeUnmount(() => {
  stopHostColumnResize?.();
});

function resetHostTableColumns() {
  resetHostColumns();
  hostColumnWidths.value = {};
}

function createHostQuickCommandDraft(command?: QuickCommand | null): QuickCommandPayload {
  return {
    name: command?.name ?? '',
    category: command?.category ?? hostQuickCommands.value[0]?.category ?? 'Linux',
    command: command?.command ?? '',
    description: command?.description ?? '',
    enabled: command?.enabled ?? true,
    sortOrder: command?.sortOrder ?? 0,
  };
}

function sortHostQuickCommands(commands: QuickCommand[]) {
  return [...commands].sort(
    (left, right) =>
      left.category.localeCompare(right.category, 'zh-Hans-CN') ||
      left.sortOrder - right.sortOrder ||
      left.id - right.id,
  );
}

async function loadHostQuickCommands() {
  isHostQuickCommandLoading.value = true;
  hostQuickCommandError.value = '';
  try {
    hostQuickCommands.value = await listQuickCommands();
    if (
      hostQuickCommandCategory.value !== 'all' &&
      !hostQuickCommands.value.some((command) => command.category === hostQuickCommandCategory.value)
    ) {
      hostQuickCommandCategory.value = 'all';
    }
  } catch (error) {
    hostQuickCommandError.value = error instanceof Error ? error.message : '快捷命令加载失败';
  } finally {
    isHostQuickCommandLoading.value = false;
  }
}

async function openHostQuickCommandManager() {
  closeHostMenus();
  hostQuickCommandManagerOpen.value = true;
  if (!hostQuickCommands.value.length && !isHostQuickCommandLoading.value) {
    await loadHostQuickCommands();
  }
}

function handleHostQuickCommandManagerOpenChange(open: boolean) {
  if (!open) closeHostQuickCommandManager();
}

function closeHostQuickCommandManager() {
  if (hostQuickCommandDialog.value.saving) return;
  hostQuickCommandManagerOpen.value = false;
  closeHostQuickCommandDialog();
}

function openHostQuickCommandDialog(command: QuickCommand | null = null) {
  hostQuickCommandDialog.value = {
    visible: true,
    mode: command ? 'edit' : 'create',
    commandId: command?.id ?? null,
    draft: createHostQuickCommandDraft(command),
    saving: false,
    error: '',
  };
}

function closeHostQuickCommandDialog(options: { force?: boolean } = {}) {
  if (hostQuickCommandDialog.value.saving && !options.force) return;
  hostQuickCommandDialog.value = {
    visible: false,
    mode: 'create',
    commandId: null,
    draft: createHostQuickCommandDraft(),
    saving: false,
    error: '',
  };
}

function hostQuickCommandPayload(draft: QuickCommandPayload): QuickCommandPayload {
  return {
    name: draft.name.trim(),
    category: draft.category.trim(),
    command: draft.command.trim(),
    description: draft.description.trim(),
    enabled: draft.enabled,
    sortOrder: draft.sortOrder,
  };
}

function handleHostQuickCommandDialogOpenChange(open: boolean) {
  if (!open) closeHostQuickCommandDialog();
}

async function saveHostQuickCommandDialog() {
  const dialog = hostQuickCommandDialog.value;
  if (!dialog.visible || dialog.saving) return;
  const payload = hostQuickCommandPayload(dialog.draft);
  if (!payload.name || !payload.category || !payload.command) {
    hostQuickCommandDialog.value = { ...dialog, error: '请填写名称、分类和命令内容' };
    return;
  }

  hostQuickCommandDialog.value = { ...dialog, saving: true, error: '' };
  try {
    const saved =
      dialog.mode === 'edit' && dialog.commandId
        ? await updateQuickCommand(dialog.commandId, payload)
        : await createQuickCommand(payload);
    const nextCommands =
      dialog.mode === 'edit'
        ? hostQuickCommands.value.map((command) => (command.id === saved.id ? saved : command))
        : [...hostQuickCommands.value, saved];
    hostQuickCommands.value = sortHostQuickCommands(nextCommands);
    hostQuickCommandCategory.value = saved.category;
    closeHostQuickCommandDialog({ force: true });
    showToast('保存成功', `快捷命令「${saved.name}」已保存。`);
  } catch (error) {
    hostQuickCommandDialog.value = {
      ...dialog,
      saving: false,
      error: error instanceof Error ? error.message : '快捷命令保存失败',
    };
  }
}

async function toggleHostQuickCommand(command: QuickCommand) {
  try {
    const saved = await updateQuickCommand(command.id, {
      name: command.name,
      category: command.category,
      command: command.command,
      description: command.description,
      enabled: !command.enabled,
      sortOrder: command.sortOrder,
    });
    hostQuickCommands.value = hostQuickCommands.value.map((item) => (item.id === saved.id ? saved : item));
  } catch (error) {
    hostQuickCommandError.value = error instanceof Error ? error.message : '快捷命令状态更新失败';
  }
}

async function moveHostQuickCommand(command: QuickCommand, direction: -1 | 1) {
  const visibleCommands = filteredHostQuickCommands.value;
  const visibleIndex = visibleCommands.findIndex((item) => item.id === command.id);
  const target = visibleCommands[visibleIndex + direction];
  if (!target) return;

  const nextCommands = [...hostQuickCommands.value];
  const sourceIndex = nextCommands.findIndex((item) => item.id === command.id);
  const targetIndex = nextCommands.findIndex((item) => item.id === target.id);
  if (sourceIndex === -1 || targetIndex === -1) return;

  [nextCommands[sourceIndex], nextCommands[targetIndex]] = [nextCommands[targetIndex], nextCommands[sourceIndex]];
  await saveHostQuickCommandOrder(nextCommands);
}

async function saveHostQuickCommandOrder(nextCommands: QuickCommand[]) {
  const previousCommands = hostQuickCommands.value;
  hostQuickCommands.value = nextCommands.map((command, index) => ({ ...command, sortOrder: (index + 1) * 10 }));
  try {
    hostQuickCommands.value = await reorderQuickCommands(hostQuickCommands.value.map((command) => command.id));
  } catch (error) {
    hostQuickCommands.value = previousCommands;
    hostQuickCommandError.value = error instanceof Error ? error.message : '快捷命令排序保存失败';
  }
}

async function removeHostQuickCommand(command: QuickCommand) {
  if (!window.confirm(`删除快捷命令「${command.name}」？`)) return;
  try {
    await deleteQuickCommand(command.id);
    hostQuickCommands.value = hostQuickCommands.value.filter((item) => item.id !== command.id);
    showToast('删除成功', `快捷命令「${command.name}」已删除。`);
  } catch (error) {
    hostQuickCommandError.value = error instanceof Error ? error.message : '快捷命令删除失败';
  }
}

function toggleFullscreen() {
  closeHostMenus();
  fullscreen.value = !fullscreen.value;
}

function setHostStatusFilter(filter: 'all' | 'unverified') {
  hostStatusFilter.value = filter;
  closeHostMoreActions();
}

async function runVerifySelectedHosts() {
  closeHostMoreActions();
  await verifySelectedManagedHosts();
}

function runMoveSelectedHosts() {
  closeHostMoreActions();
  openMoveSelectedHostsDialog();
}

function runDeleteSelectedHosts() {
  closeHostMoreActions();
  deleteSelectedManagedHosts();
}

function selectedExecutableHostIds() {
  if (!canUsePageAction('bulkExecution', 'execute')) {
    showToast('无权限', '当前账号不能发起批量执行任务。');
    return [];
  }
  const selectedIds = selectedManagedHostIds.value;
  if (!selectedIds.size) {
    showToast('请选择主机', '请先在主机管理列表中选择需要操作的主机。');
    return [];
  }

  const executableIds = managedHosts.value
    .filter((host) => selectedIds.has(host.id))
    .filter((host) => host.verified && hostPlatformType(host.platformType) === 'linux' && Boolean(host.loginUser))
    .map((host) => host.id);
  if (!executableIds.length) {
    showToast('没有可执行主机', '所选主机中没有已验证的 Linux SSH 主机。');
    return [];
  }
  return executableIds;
}

function openBulkExecutionForSelectedHosts() {
  closeHostMoreActions();
  const executableIds = selectedExecutableHostIds();
  if (!executableIds.length) return;

  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(bulkExecutionDraftTargetIdsKey, JSON.stringify(executableIds));
  }
  setActiveTool('bulkExecution');
  showToast('已进入批量执行', `已带入 ${executableIds.length} 台可执行主机。`);
}

function openBulkFileUploadForSelectedHosts() {
  closeHostMoreActions();
  const executableIds = selectedExecutableHostIds();
  if (!executableIds.length) return;

  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(bulkExecutionUploadTargetIdsKey, JSON.stringify(executableIds));
  }
  setActiveTool('bulkExecution');
  showToast('已进入文件上传', `已带入 ${executableIds.length} 台可上传主机。`);
}

function formatHostDate(value: string | null | undefined) {
  return formatDateTime(value, '-');
}

function hostPlatformType(value: string | null | undefined) {
  const type = String(value || '').toLowerCase();
  return type === 'windows' ? 'windows' : 'linux';
}
</script>

<template>
  <section v-if="activeTool === 'hosts'" class="host-manager-page" :class="{ fullscreen }" @click="closeHostMenus">
    <template v-if="canUseHostAnyAction">
    <HostGroupTree
      v-if="canUseHostList"
      :groups="hostGroups"
      :root="hostGroupRoot"
      :rows="hostGroupRows"
      :root-expanded="hostGroupRootExpanded"
      :selected-group="selectedHostGroup"
      :inline-edit="hostGroupInlineEdit"
      :menu="hostGroupMenu"
      :dragged-group-id="draggedHostGroupId"
      :drop-target="hostGroupDropTarget"
      :can-manage-groups="canUsePageAction('hosts', 'group')"
      :can-create-hosts="canUsePageAction('hosts', 'create')"
      :can-move-hosts="canUsePageAction('hosts', 'move')"
      :can-delete-hosts="canUsePageAction('hosts', 'delete')"
      :show-group-action-divider="canUseAnyPageAction('hosts', ['create', 'move', 'delete'])"
      :is-group-expanded="isHostGroupExpanded"
      @add-root="openAddRootHostGroup"
      @select-group="selectManagedGroup"
      @toggle-root="toggleHostGroupRootExpanded"
      @toggle-group="toggleHostGroupExpanded"
      @open-menu="openHostGroupMenu"
      @update-inline-name="updateHostGroupInlineName"
      @save-inline-edit="saveHostGroupInlineEdit"
      @cancel-inline-edit="cancelHostGroupInlineEdit"
      @drag-start="startHostGroupDrag"
      @drag-over="updateHostGroupDropTarget"
      @drag-leave="clearHostGroupDropTarget"
      @drop="dropHostGroup"
      @drag-end="finishHostGroupDrag"
      @add-child="openAddHostGroup"
      @rename="openRenameHostGroup"
      @add-host="addManagedHost"
      @move-host="openMoveHostDialog"
      @delete-hosts="deleteManagedHostsInGroup"
      @delete-group="deleteHostGroup"
    />

    <article v-if="canUseHostList" class="panel host-table-panel">
      <HostToolbar
        v-model:search="hostSearch"
        :status-filter="hostStatusFilter"
        :selected-count="selectedManagedHostCount"
        :more-actions-open="hostMoreActionsOpen"
        :column-settings-open="hostColumnSettingsOpen"
        :fullscreen="fullscreen"
        :columns="hostColumnOptions"
        :column-visibility="hostColumnVisibility"
        :all-columns-visible="allHostColumnsVisible"
        :some-columns-visible="someHostColumnsVisible"
        :is-only-visible-column="isOnlyVisibleHostColumn"
        :selected-verifying-count="selectedManagedHostVerifyingCount"
        :can-create="canUsePageAction('hosts', 'create')"
        :can-manage-quick-commands="canUsePageAction('hosts', 'quick_commands')"
        :can-use-more-actions="canUseHostMoreActions"
        :can-verify="canUsePageAction('hosts', 'verify')"
        :can-filter="canUsePageAction('hosts', 'filter')"
        :can-move="canUsePageAction('hosts', 'move')"
        :can-delete="canUsePageAction('hosts', 'delete')"
        :can-bulk-execute="canUsePageAction('bulkExecution', 'execute')"
        :show-more-actions-divider="canUseAnyPageAction('hosts', ['verify', 'filter']) && canUseAnyPageAction('hosts', ['move', 'delete'])"
        :can-import="canUsePageAction('hosts', 'import')"
        :can-export="canUsePageAction('hosts', 'export')"
        @create="addManagedHost()"
        @open-quick-commands="openHostQuickCommandManager"
        @toggle-more-actions="toggleHostMoreActions"
        @status-filter="setHostStatusFilter"
        @verify-selected="runVerifySelectedHosts"
        @bulk-execute-selected="openBulkExecutionForSelectedHosts"
        @upload-file-selected="openBulkFileUploadForSelectedHosts"
        @move-selected="runMoveSelectedHosts"
        @delete-selected="runDeleteSelectedHosts"
        @import="openHostTransferDialog('import')"
        @export="openHostTransferDialog('export')"
        @refresh="loadHostManagement"
        @toggle-column-settings="toggleHostColumnSettings"
        @toggle-all-columns="toggleAllHostColumns"
        @reset-columns="resetHostTableColumns"
        @update-column="updateHostColumnVisibility"
        @toggle-fullscreen="toggleFullscreen"
      />
      <HostTable
        :hosts="paginatedManagedHosts"
        :visible-host-count="visibleManagedHosts.length"
        :selected-ids="selectedManagedHostIds"
        :visible-ids="visibleHostIds"
        :all-visible-selected="allVisibleHostsSelected"
        :some-visible-selected="someVisibleHostsSelected"
        :table-style="hostTableStyle"
        :sort-key="hostSortKey"
        :sort-direction="hostSortDirection"
        :page="hostPage"
        :page-size="hostPageSize"
        :selected-count="selectedManagedHostCount"
        :selected-verifying-count="selectedManagedHostVerifyingCount"
        :stats="managedHostStats"
        :loading="isLoadingHosts"
        :verifying-ids="verifyingHostIds"
        :can-open-terminal="canUsePageAction('hosts', 'terminal')"
        :can-edit="canUsePageAction('hosts', 'edit')"
        :can-verify="canUsePageAction('hosts', 'verify')"
        :can-move="canUsePageAction('hosts', 'move')"
        :can-delete="canUsePageAction('hosts', 'delete')"
        :can-bulk-execute="canUsePageAction('bulkExecution', 'execute')"
        :can-use-row-actions="canUseHostRowActions"
        :is-column-visible="isHostColumnVisible"
        :group-name="hostGroupName"
        :sort-mark="hostSortMark"
        :format-date="formatHostDate"
        :platform-type="hostPlatformType"
        @toggle-all-visible="toggleAllVisibleHosts"
        @toggle-host="toggleHostSelected"
        @sort="setHostSort"
        @resize-column-start="startHostColumnResize"
        @open-terminal="openWebTerminal"
        @open-simple-terminal="openSimpleHostTerminal"
        @edit="editManagedHost"
        @verify="verifyManagedHost"
        @delete="deleteManagedHost"
        @page-change="setHostPage"
        @page-size-change="hostPageSize = $event"
        @clear-selection="clearSelectedManagedHosts"
        @verify-selected="runVerifySelectedHosts"
        @bulk-execute-selected="openBulkExecutionForSelectedHosts"
        @upload-file-selected="openBulkFileUploadForSelectedHosts"
        @move-selected="runMoveSelectedHosts"
        @delete-selected="runDeleteSelectedHosts"
      />
    </article>
    </template>
    <div v-else class="permission-empty">暂无可用功能</div>

    <DialogRoot
      v-if="hostQuickCommandManagerOpen"
      :open="hostQuickCommandManagerOpen"
      @update:open="handleHostQuickCommandManagerOpenChange"
    >
      <DialogPortal disabled>
        <DialogOverlay class="host-editor-overlay host-quick-command-manager-overlay" />
        <DialogContent
          class="host-editor-dialog host-quick-command-dialog"
          aria-describedby="host-quick-command-description"
          @interact-outside.prevent
        >
          <article class="host-quick-command-modal">
            <header class="host-quick-command-head popup-header">
              <div>
                <span class="host-quick-command-head-icon" aria-hidden="true">
                  <AppIcon name="zap" :size="17" />
                </span>
                <span>
                  <DialogTitle class="host-quick-command-title">快捷命令</DialogTitle>
                  <DialogDescription id="host-quick-command-description" class="host-quick-command-description">
                    管理 Web 终端中可用的快捷命令模板
                  </DialogDescription>
                </span>
              </div>
              <DialogClose as-child>
                <el-button class="host-quick-command-close" text title="关闭" aria-label="关闭">
                  <AppIcon name="x" :size="16" />
                </el-button>
              </DialogClose>
            </header>
        <div class="host-quick-command-layout popup-body">
          <aside class="host-quick-command-sidebar">
            <nav class="host-quick-command-categories" aria-label="快捷命令分类">
              <div class="host-quick-command-category-title">
                <AppIcon name="rows" :size="17" />
                <span>命令分类</span>
                <em>{{ hostQuickCommandCategories.length + 1 }} 组</em>
              </div>
              <el-menu
                class="workspace-nav-menu host-quick-command-category-list"
                :default-active="hostQuickCommandCategory"
                @select="hostQuickCommandCategory = $event"
              >
                <el-menu-item
                  index="all"
                  class="host-quick-command-category-item"
                  :aria-current="hostQuickCommandCategory === 'all' ? 'page' : undefined"
                >
                  <AppIcon name="rows" :size="17" />
                  <span class="host-quick-command-category-name">全部</span>
                  <span class="host-quick-command-category-count">{{ hostQuickCommands.length }}</span>
                </el-menu-item>
                <el-menu-item
                  v-for="category in hostQuickCommandCategories"
                  :key="category"
                  :index="category"
                  class="host-quick-command-category-item"
                  :aria-current="hostQuickCommandCategory === category ? 'page' : undefined"
                >
                  <AppIcon name="folder" :size="17" />
                  <span class="host-quick-command-category-name">{{ category }}</span>
                  <span class="host-quick-command-category-count">
                    {{ hostQuickCommands.filter((command) => command.category === category).length }}
                  </span>
                </el-menu-item>
              </el-menu>
            </nav>
          </aside>
          <section class="host-quick-command-content">
            <div class="host-quick-command-toolbar">
              <label>
                <AppIcon name="search" :size="14" />
                <el-input v-model="hostQuickCommandSearch" type="search" placeholder="搜索名称、分类或命令" clearable />
              </label>
              <span class="host-quick-command-count">{{ filteredHostQuickCommands.length }} 条</span>
              <el-button circle title="刷新" aria-label="刷新" :disabled="isHostQuickCommandLoading" @click="loadHostQuickCommands">
                <AppIcon name="refresh" :size="15" />
              </el-button>
              <el-button type="primary" @click="openHostQuickCommandDialog()">
                <AppIcon name="plus" :size="15" />
                新增
              </el-button>
            </div>
            <el-alert v-if="hostQuickCommandError" class="host-quick-command-error" type="error" :title="hostQuickCommandError" :closable="false" />
            <div class="host-quick-command-list">
              <el-empty v-if="isHostQuickCommandLoading" class="host-quick-command-empty" description="加载中..." />
              <el-empty
                v-else-if="!filteredHostQuickCommands.length"
                class="host-quick-command-empty"
                :description="hostQuickCommands.length ? '换个关键词或分类再试。' : '这里还没有命令模板。'"
              >
                <template #image>
                  <span class="host-quick-command-empty-glyph" aria-hidden="true">&gt;_</span>
                </template>
                <strong>{{ hostQuickCommands.length ? '没有匹配的命令' : '暂无快捷命令' }}</strong>
                <el-button class="host-quick-command-empty-action" type="primary" @click="openHostQuickCommandDialog()">
                  <AppIcon name="plus" :size="15" />
                  新增命令
                </el-button>
              </el-empty>
              <template v-else>
                <article
                  v-for="(command, index) in filteredHostQuickCommands"
                  :key="command.id"
                  class="host-quick-command-item"
                  :class="{ disabled: !command.enabled }"
                >
                  <div class="host-quick-command-info">
                    <div class="host-quick-command-meta">
                      <strong>{{ command.name }}</strong>
                      <span>{{ command.category }}</span>
                      <span class="host-quick-command-state">{{ command.enabled ? '启用' : '禁用' }}</span>
                    </div>
                    <code>{{ command.command }}</code>
                    <p v-if="command.description">{{ command.description }}</p>
                  </div>
                  <div class="host-quick-command-actions">
                    <el-button
                      text
                      :title="command.enabled ? '禁用' : '启用'"
                      :aria-label="command.enabled ? '禁用' : '启用'"
                      @click="toggleHostQuickCommand(command)"
                    >
                      <AppIcon :name="command.enabled ? 'eye' : 'eyeOff'" :size="14" />
                    </el-button>
                    <el-button
                      class="move-up"
                      text
                      title="上移"
                      aria-label="上移"
                      :disabled="index === 0"
                      @click="moveHostQuickCommand(command, -1)"
                    >
                      <AppIcon name="chevronDown" :size="14" />
                    </el-button>
                    <el-button
                      text
                      title="下移"
                      aria-label="下移"
                      :disabled="index === filteredHostQuickCommands.length - 1"
                      @click="moveHostQuickCommand(command, 1)"
                    >
                      <AppIcon name="chevronDown" :size="14" />
                    </el-button>
                    <el-button text title="编辑" aria-label="编辑" @click="openHostQuickCommandDialog(command)">
                      <AppIcon name="edit" :size="14" />
                    </el-button>
                    <el-button text title="删除" aria-label="删除" @click="removeHostQuickCommand(command)">
                      <AppIcon name="trash" :size="14" />
                    </el-button>
                  </div>
                </article>
              </template>
            </div>
          </section>
        </div>
          </article>
        </DialogContent>
      </DialogPortal>
    </DialogRoot>

    <DialogRoot
      v-if="hostQuickCommandDialog.visible"
      :open="hostQuickCommandDialog.visible"
      @update:open="handleHostQuickCommandDialogOpenChange"
    >
      <DialogPortal disabled>
        <DialogOverlay class="host-editor-overlay host-quick-command-editor-overlay" />
        <DialogContent
          class="host-editor-dialog host-quick-command-editor-dialog"
          aria-describedby="host-quick-command-editor-description"
          @interact-outside.prevent
          @escape-key-down="hostQuickCommandDialog.saving && $event.preventDefault()"
        >
          <header class="host-editor-header">
            <div class="host-editor-heading">
              <span class="host-editor-heading-icon">
                <AppIcon name="terminal" :size="20" />
              </span>
              <div>
                <DialogTitle class="host-editor-title">
                  {{ hostQuickCommandDialog.mode === 'edit' ? '编辑快捷命令' : '新增快捷命令' }}
                </DialogTitle>
                <DialogDescription id="host-quick-command-editor-description" class="host-editor-description">
                  配置终端中可快速填充或直接执行的命令模板。
                </DialogDescription>
              </div>
            </div>
            <DialogClose as-child>
              <el-button
                class="host-editor-icon-button"
                text
                title="关闭"
                aria-label="关闭"
                :disabled="hostQuickCommandDialog.saving"
              >
                <AppIcon name="x" :size="18" />
              </el-button>
            </DialogClose>
          </header>

          <form
            id="host-quick-command-editor-form"
            class="host-form-modal host-editor-form host-quick-command-form popup-body popup-form-grid"
            @submit.prevent="saveHostQuickCommandDialog"
          >
            <el-alert
              v-if="hostQuickCommandDialog.error"
              class="host-quick-command-error"
              type="error"
              :title="hostQuickCommandDialog.error"
              :closable="false"
            />
            <section class="host-editor-section host-quick-command-editor-section">
              <div class="host-editor-section-head">
                <span class="host-editor-section-icon">
                  <AppIcon name="zap" :size="17" />
                </span>
                <div>
                  <h3>命令信息</h3>
                  <p>设置易于识别的名称和分类，便于在终端中快速查找。</p>
                </div>
              </div>
              <div class="host-editor-section-grid host-quick-command-editor-grid">
                <label class="host-horizontal-field required">
                  <span>名称</span>
                  <el-input
                    v-model="hostQuickCommandDialog.draft.name"
                    autofocus
                    placeholder="例如：查看系统负载"
                    :disabled="hostQuickCommandDialog.saving"
                  />
                </label>
                <div class="host-horizontal-field required">
                  <span>分类</span>
                  <el-select
                    v-model="hostQuickCommandDialog.draft.category"
                    filterable
                    allow-create
                    default-first-option
                    placeholder="选择或输入分类"
                    :teleported="false"
                    :disabled="hostQuickCommandDialog.saving"
                  >
                    <el-option v-for="category in hostQuickCommandCategories" :key="category" :value="category" :label="category" />
                  </el-select>
                </div>
                <label class="host-horizontal-field required host-editor-span-2">
                  <span>命令</span>
                  <el-input
                    v-model="hostQuickCommandDialog.draft.command"
                    type="textarea"
                    :rows="5"
                    placeholder="输入需要在终端中执行的命令"
                    :disabled="hostQuickCommandDialog.saving"
                  />
                </label>
                <label class="host-horizontal-field host-editor-span-2">
                  <span>说明</span>
                  <el-input
                    v-model="hostQuickCommandDialog.draft.description"
                    placeholder="补充命令用途或执行注意事项（可选）"
                    :disabled="hostQuickCommandDialog.saving"
                  />
                </label>
              </div>
            </section>

            <section class="host-quick-command-status">
              <div>
                <strong>启用快捷命令</strong>
                <span>启用后，此命令会出现在 Web 终端快捷命令列表中。</span>
              </div>
              <el-switch
                v-model="hostQuickCommandDialog.draft.enabled"
                :disabled="hostQuickCommandDialog.saving"
                aria-label="启用快捷命令"
              />
            </section>
          </form>

          <footer class="host-form-actions host-editor-actions popup-footer popup-actions">
            <DialogClose as-child>
              <el-button
                class="host-editor-button host-editor-button-outline"
                native-type="button"
                :disabled="hostQuickCommandDialog.saving"
              >
                取消
              </el-button>
            </DialogClose>
            <el-button
              form="host-quick-command-editor-form"
              class="host-editor-button host-editor-button-primary"
              native-type="submit"
              :loading="hostQuickCommandDialog.saving"
              :disabled="hostQuickCommandDialog.saving"
            >
              {{ hostQuickCommandDialog.saving ? '保存中...' : '保存命令' }}
            </el-button>
          </footer>
        </DialogContent>
      </DialogPortal>
    </DialogRoot>

    <HostEditorDialog
      :dialog="hostDialog"
      :form="hostForm"
      :errors="hostFormErrors"
      :root="hostGroupRoot"
      :groups="flatHostGroups"
      :credentials="hostCredentials"
      @close="hostDialog = null"
      @submit="saveManagedHost"
      @update-form-field="updateHostFormField"
      @apply-credential="applyCredentialToHostForm"
      @upload-private-key="uploadHostPrivateKey"
    />

    <HostMoveDialog
      :open="hostMoveDialogOpen"
      :mode="hostMoveMode"
      :form="hostMoveForm"
      :hosts="groupMoveHosts"
      :root="hostGroupRoot"
      :groups="flatHostGroups"
      :selected-count="selectedManagedHostCount"
      @close="hostMoveDialogOpen = false"
      @submit="saveMoveManagedHost"
      @update-form-field="updateHostMoveFormField"
    />
  </section>
</template>
