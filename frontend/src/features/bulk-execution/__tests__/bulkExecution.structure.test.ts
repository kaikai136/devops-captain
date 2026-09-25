import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function readSource(relativePath: string) {
  return readFileSync(new URL(`../../../${relativePath}`, import.meta.url), 'utf8');
}

describe('bulk execution frontend contract', () => {
  it('registers bulkExecution as a host-management sibling page in navigation and app shell', () => {
    const types = readSource('types.ts');
    const navigation = readSource('app/navigation.ts');
    const shellState = readSource('composables/app/useShellState.ts');
    const app = readSource('App.vue');

    expect(types).toContain("'bulkExecution'");
    expect(navigation).toContain("key: 'bulkExecution' as const");
    expect(navigation).toMatch(/sessionAudits[\s\S]+bulkExecution[\s\S]+accounts/);
    expect(shellState).toMatch(/bulkExecution:\s*'(terminal|zap)'/);
    expect(app).toContain('BulkExecutionPanel');
    expect(app).toContain("activeTool === 'bulkExecution'");
  });

  it('exposes typed API helpers for targets, task creation, polling, cancel, and delete', () => {
    const api = readSource('features/bulk-execution/api/bulkExecution.ts');
    const types = readSource('features/bulk-execution/types.ts');

    expect(types).toContain('BulkExecutionTarget');
    expect(types).toContain('BulkExecutionTargetGroup');
    expect(types).toContain('BulkExecutionTargetTree');
    expect(types).toContain('BulkExecutionTaskDetail');
    expect(api).toContain('/api/bulk-execution');
    expect(api).toContain('listBulkExecutionTargets');
    expect(api).toContain('listBulkExecutionTargetTree');
    expect(api).toContain('/target-tree/');
    expect(api).toContain('createBulkExecutionTask');
    expect(api).toContain('listBulkExecutionTasks');
    expect(api).toContain('getBulkExecutionTask');
    expect(api).toContain('cancelBulkExecutionTask');
    expect(api).toContain('deleteBulkExecutionTask');
  });

  it('exposes upload check, multipart upload helpers, and typed upload metadata', () => {
    const api = readSource('features/bulk-execution/api/bulkExecution.ts');
    const types = readSource('features/bulk-execution/types.ts');

    expect(types).toContain("BulkExecutionType = 'shell' | 'file_upload'");
    expect(types).toContain('BulkFileUploadCreatePayload');
    expect(types).toContain('BulkUploadCheckResult');
    expect(types).toContain('BulkExecutionUploadFile');
    expect(types).toContain('BulkTransferItem');
    expect(types).toContain('remoteDirectory');
    expect(types).toContain('uploadFilename');
    expect(types).toContain('uploadSize');
    expect(types).toContain('files: File[]');
    expect(api).toContain('createBulkFileUploadTask');
    expect(api).toContain('checkBulkFileUpload');
    expect(api).toContain('/uploads/check/');
    expect(api).toContain('FormData');
    expect(api).toContain("form.append('executionType', 'file_upload')");
    expect(api).toContain("form.append('files'");
    expect(api).toContain("form.append('overwrite'");
  });

  it('adds host-list shortcuts that store selected hosts and open the bulk execution page', () => {
    const manager = readSource('features/hosts/components/HostManager.vue');
    const table = readSource('features/hosts/components/HostTable.vue');
    const toolbar = readSource('features/hosts/components/HostToolbar.vue');

    expect(manager).toContain('ops-tool.bulk-execution.draft-target-ids');
    expect(manager).toContain('ops-tool.bulk-execution.upload-target-ids');
    expect(manager).toContain("setActiveTool('bulkExecution')");
    expect(manager).toContain("canUsePageAction('bulkExecution', 'execute')");
    expect(table).toContain('bulk-execute-selected');
    expect(table).not.toContain('upload-file-selected');
    expect(toolbar).toContain('canBulkExecute');
    expect(toolbar).toContain('bulk-execute-selected');
    expect(toolbar).toContain('upload-file-selected');
  });

  it('defines the redesigned page surface with history, execute, and upload views', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const types = readSource('features/bulk-execution/types.ts');

    expect(panel).toContain('bulk-execution-page');
    expect(panel).toContain('activeBulkView');
    expect(panel).toContain('bulk-execution-actions');
    expect(panel).not.toContain('bulk-view-tabs');
    expect(panel).toContain('bulk-history-view');
    expect(panel).toContain('bulk-record-panel');
    expect(panel).toContain('bulk-record-table');
    expect(panel).toContain('bulk-status-filter');
    expect(panel).toContain('isTaskDetailOpen');
    expect(panel).toContain('<el-dialog v-model="isTargetPickerOpen"');
    expect(panel).toContain('v-model="isTaskDetailOpen"');
    expect(panel).not.toContain('<el-drawer v-model="isTaskDetailOpen"');
    expect(panel).toContain('bulk-execute-view');
    expect(panel).toContain('bulk-upload-view');
    expect(panel).toContain('taskHistory');
    expect(panel).toContain('selectedTargetIds');
    expect(panel).toContain('commandInput');
    expect(panel).toContain('requestConfirm');
    expect(panel).toContain('stdout');
    expect(panel).toContain('stderr');
    expect(panel).not.toContain('playbook');
    expect(types).not.toContain('logOutput');
    expect(panel).toContain('setInterval');
  });

  it('keeps task detail large with a scrollable shell command block', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');

    expect(panel).toContain('bulk-task-detail-modal');
    expect(panel).toContain('bulk-command-block');
    expect(styles).toContain('width: min(1440px, calc(100vw - 48px))');
    expect(styles).toContain('height: min(880px, calc(100dvh - 48px))');
    expect(styles).toContain('.bulk-task-detail-modal .el-dialog__body');
    expect(styles).toContain('overflow-x: hidden');
    expect(styles).toContain('max-height: clamp(170px, 24vh, 280px)');
    expect(styles).toContain('white-space: pre');
    expect(styles).toContain('word-break: normal');
  });

  it('does not expose the removed playbook execution surface', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const types = readSource('features/bulk-execution/types.ts');

    expect(types).not.toContain("'playbook'");
    expect(panel).not.toContain('Playbook');
  });

  it('uses a confirm-only target picker modal instead of rendering the full host list inline', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');

    const executeView = panel.match(/<section v-show="activeBulkView === 'execute'"[\s\S]*?<footer class="bulk-workbench-footer">/)?.[0] ?? '';
    const uploadView = panel.match(/<section v-show="activeBulkView === 'upload'"[\s\S]*?<footer class="bulk-workbench-footer">/)?.[0] ?? '';
    const pickerModal = panel.match(/<el-dialog v-model="isTargetPickerOpen"[\s\S]*?<\/el-dialog>/)?.[0] ?? '';

    expect(panel).toContain('const isTargetPickerOpen = ref(false)');
    expect(panel).toContain('const draftTargetIds = ref<Set<number>>(new Set())');
    expect(panel).toContain('const targetGroupFilter = ref<number | null>(null)');
    expect(panel).toContain("const targetPickerKeyword = ref('')");
    expect(panel).toContain('const targetGroups = ref<BulkExecutionTargetGroup[]>([])');
    expect(panel).toContain('openTargetPicker');
    expect(panel).toContain('confirmTargetSelection');
    expect(panel).toContain('closeTargetPicker');
    expect(panel).toContain('selectedTargetIds.value = new Set(draftTargetIds.value)');
    expect(panel).toContain('draftTargetIds.value = new Set(selectedTargetIds.value)');
    expect(executeView).toContain('bulk-target-summary');
    expect(uploadView).toContain('bulk-target-summary');
    expect(executeView).not.toContain('v-for="target in filteredTargets"');
    expect(uploadView).not.toContain('v-for="target in filteredTargets"');
    expect(pickerModal).toContain('bulk-target-picker-modal');
    expect(pickerModal).toContain('bulk-target-group-tree');
    expect(pickerModal).toContain('targetPickerKeyword');
    expect(pickerModal).toContain('toggleAllPickerTargetsFromEvent');
    expect(pickerModal).toContain('confirmTargetSelection');
    expect(pickerModal).toContain('closeTargetPicker');
    expect(pickerModal).not.toContain('@click.self');
  });

  it('renders the target picker results as a dense host-style list instead of spaced cards', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');
    const pickerListStyles = styles.match(/\.bulk-target-picker-list \{[\s\S]*?\}/)?.[0] ?? '';
    const pickerRowStyles = styles.match(/\.bulk-target-picker-row \{[\s\S]*?\}/)?.[0] ?? '';

    expect(panel).toContain('bulk-target-picker-row');
    expect(panel).toContain('toggleAllPickerTargetsFromEvent');
    expect(pickerListStyles).toContain('gap: 0');
    expect(pickerListStyles).toContain('border: 1px solid var(--bulk-soft-line)');
    expect(pickerListStyles).toContain('background: var(--bulk-panel)');
    expect(pickerListStyles).toContain('overflow-y: auto');
    expect(pickerRowStyles).toContain('grid-template-columns: 18px minmax(0, 1fr) minmax(92px, 120px) minmax(92px, 116px) minmax(84px, 110px)');
    expect(pickerRowStyles).toContain('min-height: 36px');
    expect(pickerRowStyles).toContain('border-bottom: 1px solid var(--bulk-soft-line)');
    expect(pickerRowStyles).toContain('border-radius: 0');
    expect(pickerRowStyles).toContain('padding: 0 10px');
    expect(pickerRowStyles).not.toContain('border: 1px solid #d6dfeb');
    expect(pickerRowStyles).not.toContain('gap: 4px 8px');
  });

  it('renders selected targets as single-line rows with inline metadata and a dedicated remove action', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');
    const selectedTargetListStyles = styles.match(/\.bulk-selected-target-list \{[\s\S]*?\}/)?.[0] ?? '';
    const selectedTargetRowStyles = styles.match(/\.bulk-selected-target-row \{[\s\S]*?\}/)?.[0] ?? '';
    const selectedTargetMainStyles = styles.match(/\.bulk-selected-target-main \{[\s\S]*?\}/)?.[0] ?? '';
    const selectedTargetMetaStyles = styles.match(/\.bulk-selected-target-meta \{[\s\S]*?\}/)?.[0] ?? '';

    expect(panel).toContain('bulk-selected-target-main');
    expect(panel).toContain('bulk-selected-target-name');
    expect(panel).toContain('bulk-selected-target-meta');
    expect(panel).toContain('bulk-selected-target-ip');
    expect(panel).toContain('bulk-selected-target-user');
    expect(panel).toContain('bulk-selected-target-group');
    expect(panel).toContain('bulk-selected-target-remove');
    expect(panel).toContain('aria-label="移除目标机器"');
    expect(selectedTargetListStyles).toContain('max-height: 330px');
    expect(selectedTargetListStyles).toContain('border: 1px solid var(--bulk-soft-line)');
    expect(selectedTargetListStyles).toContain('overflow-y: auto');
    expect(selectedTargetListStyles).toContain('gap: 0');
    expect(selectedTargetRowStyles).toContain('grid-template-columns: minmax(0, 1fr) minmax(92px, 116px) minmax(64px, 84px) minmax(84px, 110px) 34px');
    expect(selectedTargetRowStyles).toContain('border-bottom: 1px solid var(--bulk-soft-line)');
    expect(selectedTargetRowStyles).toContain('border-radius: 0');
    expect(selectedTargetRowStyles).not.toContain('transform: translateY(-1px)');
    expect(selectedTargetMainStyles).toContain('display: contents');
    expect(selectedTargetMetaStyles).toContain('display: contents');
    expect(styles).toContain('.bulk-selected-target-remove');
  });

  it('keeps view navigation in the top actions with record before execute and upload', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const actions = panel.match(/<el-button-group class="bulk-execution-actions">[\s\S]*?<\/el-button-group>/)?.[0] ?? '';

    expect(actions).toContain("activeBulkView === 'history'");
    expect(actions).toContain("activeBulkView === 'execute'");
    expect(actions).toContain("activeBulkView === 'upload'");
    expect(actions).toContain('执行记录');
    expect(actions).toContain('新建执行');
    expect(actions).toContain('批量上传');
    expect(actions.indexOf('执行记录')).toBeLessThan(actions.indexOf('新建执行'));
    expect(actions.indexOf('新建执行')).toBeLessThan(actions.indexOf('批量上传'));
    expect(actions.indexOf('批量上传')).toBeLessThan(actions.indexOf('@click="refreshAll"'));
  });

  it('keeps history filters aligned in the record toolbar before refresh without the duplicate execute action', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');
    const toolbar = panel.match(/<header class="bulk-record-toolbar">[\s\S]*?<\/header>/)?.[0] ?? '';
    const actions = panel.match(/<div class="bulk-record-actions">[\s\S]*?<\/div>/)?.[0] ?? '';
    const toolbarStyles = styles.match(/\.bulk-record-toolbar \{[\s\S]*?\}/)?.[0] ?? '';
    const actionsStyles = styles.match(/\.bulk-record-actions \{[\s\S]*?\}/)?.[0] ?? '';

    expect(panel).not.toContain('<section class="bulk-execution-filters">');
    expect(actions).toContain('bulk-keyword-filter');
    expect(actions).toContain('bulk-host-filter');
    expect(toolbar).toContain('bulk-status-filter');
    expect(toolbar).toContain('<el-input v-model="keyword"');
    expect(toolbar).toContain('<el-select v-model="hostFilter"');
    expect(toolbar).toContain('<el-select v-model="statusFilter"');
    expect(toolbar).toContain('v-model="keyword"');
    expect(toolbar).toContain('v-model="hostFilter"');
    expect(actions).toContain('bulk-status-filter');
    expect(toolbar).toContain('v-model="statusFilter"');
    expect(toolbar).toContain('@change="setHistoryStatus(statusFilter)"');
    expect(actions.indexOf('bulk-keyword-filter')).toBeLessThan(actions.indexOf('bulk-host-filter'));
    expect(actions.indexOf('bulk-host-filter')).toBeLessThan(actions.indexOf('bulk-status-filter'));
    expect(actions.indexOf('bulk-status-filter')).toBeLessThan(actions.indexOf('@click="refreshAll"'));
    expect(toolbar).not.toContain('bulk-status-tabs');
    expect(toolbar).not.toContain('openCreateDialog');
    expect(toolbar).not.toContain('>批量执行</button>');
    expect(toolbarStyles).toContain('grid-template-columns: minmax(0, 1fr) auto');
    expect(actionsStyles).toContain('display: flex');
    expect(actionsStyles).toContain('align-items: center');
    expect(actionsStyles).toContain('flex-wrap: nowrap');
    expect(styles).toContain('.bulk-keyword-filter,');
    expect(styles).toContain('--bulk-control-h: 36px');
    expect(styles).toContain('box-sizing: border-box');
    expect(panel).toContain("{ value: '', label: '全部状态' }");

    const filterStyles = styles.match(/\.bulk-keyword-filter,\s*\.bulk-host-filter,\s*\.bulk-status-filter \{[\s\S]*?\}/)?.[0] ?? '';
    const controlStyles = styles.match(/\.bulk-keyword-filter input,\s*\.bulk-host-filter select,\s*\.bulk-status-filter select \{[\s\S]*?\}/)?.[0] ?? '';
    const buttonStyles = styles.match(/\.bulk-record-actions button \{[\s\S]*?\}/)?.[0] ?? '';

    for (const block of [filterStyles, controlStyles, buttonStyles]) {
      expect(block).toContain('height: var(--bulk-control-h)');
      expect(block).toContain('min-height: var(--bulk-control-h)');
      expect(block).toContain('margin: 0');
    }
    expect(filterStyles).toContain('align-self: center');
    expect(buttonStyles).toContain('align-self: center');
  });

  it('selects execution records with host-list style checkboxes and shows a bottom bulk delete bar', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');
    const recordTable = panel.match(/<div class="bulk-record-table[^\"]*">[\s\S]*?<\/div>\s*<footer class="bulk-record-footer">/)?.[0] ?? '';

    expect(panel).toContain('const selectedRecordTaskIds = ref<Set<number>>(new Set())');
    expect(panel).toContain('visibleRecordTaskIds');
    expect(panel).toContain('allVisibleRecordsSelected');
    expect(panel).toContain('someVisibleRecordsSelected');
    expect(panel).toContain('toggleAllVisibleRecordTasks');
    expect(panel).toContain('toggleRecordTaskSelection');
    expect(panel).toContain('clearSelectedRecordTasks');
    expect(panel).toContain('deleteSelectedRecordTasks');
    expect(recordTable).toContain('bulk-record-select-cell');
    expect(recordTable).toContain(':model-value="allVisibleRecordsSelected"');
    expect(recordTable).toContain(':indeterminate="someVisibleRecordsSelected && !allVisibleRecordsSelected"');
    expect(recordTable).toContain('@change="toggleAllVisibleRecordTasks"');
    expect(recordTable).toContain(':model-value="selectedRecordTaskIds.has(row.id)"');
    expect(recordTable).toContain('@change="toggleRecordTaskSelection(row.id, $event)"');
    expect(recordTable).not.toContain(':model-value="selectedTaskId === row.id"');
    expect(panel).not.toContain(":class=\"{ 'has-record-selection': selectedRecordTaskIds.size }\"");
    expect(panel).toContain('host-bulk-action-bar bulk-record-bulk-action-bar');
    expect(panel).toContain('已选择 {{ selectedRecordTaskIds.size }} 个任务');
    expect(panel).toContain('@click="clearSelectedRecordTasks"');
    expect(panel).toContain('@click="deleteSelectedRecordTasks"');
    expect(panel).toContain('取消所选');
    expect(panel).toContain('删除所选');
    expect(styles).toContain('.bulk-record-select-cell');
    expect(styles).toContain('.bulk-record-bulk-action-bar');
    expect(styles).not.toContain('.bulk-record-panel.has-record-selection .bulk-record-footer');
    expect(styles).not.toContain('padding-bottom: 112px');
    expect(styles).toContain('position: absolute');
    expect(styles).toContain('bottom: 14px');
    expect(styles).toContain('transform: translateX(-50%)');
    expect(styles).not.toContain('pointer-events: none');
  });

  it('numbers execution records after the selection column using the current page offset', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');
    const recordTable = panel.match(/<div class="bulk-record-table[^\"]*">[\s\S]*?<\/div>\s*<footer class="bulk-record-footer">/)?.[0] ?? '';
    const selectionColumnIndex = recordTable.indexOf('width="54"');
    const numberColumnIndex = recordTable.indexOf('width="80" align="center"');
    const hostColumnIndex = recordTable.indexOf('min-width="150"');

    expect(recordTable).toContain('<el-table :data="taskHistory"');
    expect(recordTable).toContain('<el-table-column width="54" align="center">');
    expect(recordTable).toContain('width="80" align="center"');
    expect(recordTable).toContain('<template #default="{ $index }">{{ taskPageStart + $index }}</template>');
    expect(selectionColumnIndex).toBeGreaterThanOrEqual(0);
    expect(numberColumnIndex).toBeGreaterThan(selectionColumnIndex);
    expect(hostColumnIndex).toBeGreaterThan(numberColumnIndex);
    expect(recordTable).toContain('class="bulk-record-table app-data-table-wrap"');
    expect(recordTable).toContain('class="bulk-record-grid app-data-table"');
    expect(styles).toMatch(/\.bulk-record-grid\s*\{\s*min-width:\s*1388px;/);
    expect(styles).not.toMatch(/^\.bulk-record-grid thead th\s*\{/m);
    expect(styles).not.toMatch(/^\.bulk-record-grid th,\s*$/m);
  });

  it('uses the detail modal primary action to expand or collapse all host outputs', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const detailModal = panel.match(/<el-dialog[\s\S]*?v-model="isTaskDetailOpen"[\s\S]*?<\/el-dialog>/)?.[0] ?? '';

    expect(panel).toContain('allResultsExpanded');
    expect(panel).toContain('toggleAllResults');
    expect(detailModal).toContain('@click="toggleAllResults"');
    expect(detailModal).toContain("{{ allResultsExpanded ? '全部收起' : '全部展开' }}");
    expect(detailModal).not.toContain('@click="rerunTask(selectedTask)"');
  });

  it('paginates bulk task history with the shared footer pattern and right-side task statistics', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const footer = panel.match(/<footer class="bulk-record-footer">[\s\S]*?<\/footer>/)?.[0] ?? '';

    expect(panel).toContain('const taskPage = ref(1)');
    expect(panel).toContain('const taskPageSize = ref(10)');
    expect(panel).toContain('const taskTotal = ref(0)');
    expect(panel).toContain('page: taskPage.value');
    expect(panel).toContain('pageSize: taskPageSize.value');
    expect(panel).toContain('taskTotal.value = page.count');
    expect(panel).toContain('setTaskPage');
    expect(panel).toContain('setTaskPageSize');
    expect(footer).toContain('<AppPagination');
    expect(footer).toContain('host-pagination');
    expect(footer).toContain('bulk-record-stats');
    expect(footer).toContain('{{ taskTotal }} 个任务 · {{ targets.length }} 台可执行主机');
  });

  it('defines the upload page pre-check flow and multi-file target handoff', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');

    expect(panel).toContain('uploadTargetIdsKey');
    expect(panel).toContain('selectedUploadFiles');
    expect(panel).toContain('remoteDirectory');
    expect(panel).toContain('uploadCheckResult');
    expect(panel).toContain('checkBulkUpload');
    expect(panel).toContain('duplicateFiles');
    expect(panel).toContain('unreachableTargets');
    expect(panel).toContain('overwriteConfirmed');
    expect(panel).toContain('createBulkFileUploadTask');
    expect(panel).toContain('bulk-upload-dropzone');
    expect(panel).toContain('bulk-upload-check-panel');
    expect(panel).toContain('type="file"');
    expect(panel).toContain('multiple');
    expect(panel).toContain('开始上传');
  });

  it('marks required bulk fields and validates actions on click', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');

    expect(panel).toContain('required-marker');
    expect(panel).toContain('validateExecuteForm');
    expect(panel).toContain('validateUploadForm');
    expect(panel).toContain('请填写任务名称');
    expect(panel).toContain('请选择目标机器');
    expect(panel).toContain('请填写脚本内容');
    expect(panel).toContain('请选择上传文件或文件夹');
    expect(panel).toContain('请填写远程目录');
    expect(panel).toContain('@click="createTaskWithConfirmation"');
    expect(panel).toContain('@click="submitUploadFlow"');
  });

  it('keeps execute confirmations summary-only without exposing script content', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const confirmationFlow = panel.match(/function createTaskWithConfirmation\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';

    expect(confirmationFlow).toContain('将对 ${selectedTargetIds.value.size} 台主机执行批量任务。');
    expect(confirmationFlow).not.toContain('${executionTypeLabels[executionType.value]}');
    expect(confirmationFlow).not.toContain('commandInput.value.trim()');
  });

  it('supports folder selection and preserves relative paths through upload APIs', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const api = readSource('features/bulk-execution/api/bulkExecution.ts');
    const types = readSource('features/bulk-execution/types.ts');

    expect(panel).toContain('uploadFolderInput');
    expect(panel).toContain('webkitdirectory');
    expect(panel).toContain('webkitRelativePath');
    expect(panel).toContain('relativePaths');
    expect(panel).toContain('relativePathForFile');
    expect(api).toContain("form.append('relativePaths'");
    expect(types).toContain('relativePaths');
  });

  it('shows the selected upload files as a direct compact scroll list so the remote directory remains visible', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');

    expect(panel).not.toContain('isUploadFileListExpanded');
    expect(panel).not.toContain('toggleUploadFileList');
    expect(panel).toContain('bulk-upload-file-summary');
    expect(panel).toContain('bulk-upload-file-list-scroll');
    expect(panel).toContain('bulk-upload-file-name');
    expect(panel).not.toContain('文件列表');
    expect(styles).toContain('.bulk-upload-file-list-scroll');
    expect(styles).toContain('overflow-y: auto');
    expect(styles).toContain('max-height: clamp');
    expect(styles).not.toContain('gap: 8px;\n  max-height: clamp');
  });

  it('renders upload transfer details on each task result', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const types = readSource('features/bulk-execution/types.ts');

    expect(types).toContain('transfers: BulkTransferItem[]');
    expect(panel).toContain('result.transfers');
    expect(panel).toContain('bulk-transfer-matrix');
    expect(panel).toContain('transfer.remotePath');
  });

  it('switches upload task detail between hosts, file tree, and remote directory with size as read-only summary', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');
    const detailSwitch = panel.match(/<div v-if="selectedTask.executionType === 'file_upload'" class="bulk-upload-detail-switch"[\s\S]*?<\/div>/)?.[0] ?? '';
    const treeStyles = styles.match(/\.bulk-upload-detail-tree \{[\s\S]*?\}/)?.[0] ?? '';

    expect(panel).toContain("type UploadDetailView = 'hosts' | 'files' | 'directory'");
    expect(panel).toContain("const uploadDetailView = ref<UploadDetailView>('hosts')");
    expect(panel).toContain('expandedUploadFolderKeys');
    expect(panel).toContain('buildUploadFileTree');
    expect(panel).toContain('uploadFileTreeRows');
    expect(panel).toContain('toggleUploadFolder');
    expect(detailSwitch).toContain("setUploadDetailView('hosts')");
    expect(detailSwitch).toContain("setUploadDetailView('files')");
    expect(detailSwitch).toContain("setUploadDetailView('directory')");
    expect(detailSwitch).toContain('bulk-upload-detail-size');
    expect(detailSwitch).not.toContain("setUploadDetailView('size')");
    expect(detailSwitch.indexOf("setUploadDetailView('hosts')")).toBeLessThan(detailSwitch.indexOf("setUploadDetailView('files')"));
    expect(detailSwitch.indexOf("setUploadDetailView('files')")).toBeLessThan(detailSwitch.indexOf("setUploadDetailView('directory')"));
    expect(detailSwitch.indexOf("setUploadDetailView('directory')")).toBeLessThan(detailSwitch.indexOf('bulk-upload-detail-size'));
    expect(panel).toContain("uploadDetailView === 'files'");
    expect(panel).toContain('bulk-upload-detail-tree');
    expect(panel).toContain('bulk-upload-tree-row');
    expect(panel).toContain("'folderOpen'");
    expect(panel).not.toContain('class="bulk-upload-file-list"');
    expect(styles).toContain('.bulk-upload-detail-switch');
    expect(treeStyles).toContain('display: block');
    expect(treeStyles).toContain('flex: 1 1 auto');
    expect(treeStyles).toContain('min-height: 0');
    expect(treeStyles).toContain('overflow: auto');
    expect(treeStyles).not.toContain('max-height: min(340px, 42vh)');
    expect(styles).toContain('.bulk-upload-tree-row');
    expect(styles).toContain('.bulk-upload-tree-toggle');
    expect(styles).toContain('display: flex');
    expect(styles).toContain('justify-content: flex-start');
  });

  it('supports shell scripts in the task composer', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const types = readSource('features/bulk-execution/types.ts');

    expect(types).toContain("BulkExecutionType = 'shell' | 'file_upload'");
    expect(types).toContain('executionType');
    expect(panel).toContain('executionType');
    expect(panel).toContain('Shell');
    expect(panel).not.toContain('Playbook');
    expect(panel).toContain('scriptPresets');
    expect(panel).toContain('executionType: executionType.value');
    expect(panel).toContain('taskName.value.trim().length > 0');
    expect(panel).toContain('name: taskName.value.trim()');
    expect(panel).toContain('scriptFileInput');
    expect(panel).toContain('scriptSourceName');
    expect(panel).toContain('scriptFileAccept');
    expect(panel).toContain('triggerScriptFileSelect');
    expect(panel).toContain('onScriptFileChange');
    expect(panel).toContain('file.text()');
    expect(panel).toContain('bulk-script-source');
    expect(panel).toContain('bulk-script-upload-button');
    expect(panel).toContain('placeholder="请输入任务名称"');
    expect(panel).toContain('required');
    expect(panel).toContain('MAX_SCRIPT_LENGTH = 200000');
  });

  it('adds a clear action beside script upload that resets the editor and source label', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const styles = readSource('styles/tools/bulk-execution.css');
    const editorHead = panel.match(/<div class="bulk-script-editor-head">[\s\S]*?<\/div>\s*<\/div>\s*<div v-if="scriptSourceName"/)?.[0] ?? '';
    const clearFunction = panel.match(/function clearScriptInput\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';

    expect(panel).toContain('canClearScriptInput');
    expect(clearFunction).toContain("commandInput.value = ''");
    expect(clearFunction).toContain("scriptSourceName.value = ''");
    expect(editorHead).toContain('bulk-script-editor-actions');
    expect(editorHead).toContain('bulk-script-upload-button');
    expect(editorHead).toContain('bulk-script-clear-button');
    expect(editorHead).toContain('@click="clearScriptInput"');
    expect(editorHead).toContain('aria-label="清空脚本内容"');
    expect(editorHead).toContain('!canClearScriptInput');
    expect(styles).toContain('.bulk-script-editor-actions');
    expect(styles).toContain('.bulk-script-clear-button');
  });

  it('keeps task polling lightweight and shows success and failure counts in the status column', () => {
    const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
    const loadTasksStart = panel.indexOf('async function loadTasks() {');
    const selectTaskStart = panel.indexOf('async function selectTask(');
    const listLoader = loadTasksStart >= 0 && selectTaskStart > loadTasksStart ? panel.slice(loadTasksStart, selectTaskStart) : '';
    const polling = panel.match(/function startPolling\(\)[\s\S]*?function stopPolling/)?.[0] ?? '';
    const statusColumn = panel.match(/<el-table-column label="[^"]*" min-width="120" align="center">[\s\S]*?<\/el-table-column>/)?.[0] ?? '';

    expect(listLoader).not.toContain('await selectTask(');
    expect(panel).toContain('const pollInFlight = ref(false)');
    expect(polling).toContain('if (pollInFlight.value) return');
    expect(polling).toContain('isTaskDetailOpen.value');
    expect(polling).toContain('5000');
    expect(panel).toContain('function taskResultSummary(task: BulkExecutionTask)');
    expect(statusColumn).toContain('{{ taskResultSummary(row) }}');
    expect(statusColumn).not.toContain('{{ statusLabel(row.status) }}');
  });
});
