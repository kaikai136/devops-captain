<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus';
import { Bell, Download, RefreshCw, Trash2, X } from '@lucide/vue';
import { errorMessage } from '@shared/utils/errors';
import {
  beginDatabaseTransferUpload, cancelDatabaseTransfer, confirmDatabaseTransfer,
  createDatabaseTransfer, databaseTransferDownloadUrl, deleteDatabaseTransfer,
  listDatabaseTransferTasks, retryDatabaseTransfer, uploadDatabaseTransferChunk,
  completeDatabaseTransferUpload, type DatabaseTransferTask,
} from '../api/databaseManagement';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ 'update:open': [value: boolean] }>();
const tasks = ref<DatabaseTransferTask[]>([]);
const loading = ref(false);
const filter = ref('all');
const policy = ref<Record<string, string>>({});
const confirming = ref('');
const popoverVisible = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
});
const visibleTasks = computed(() => filter.value === 'all' ? tasks.value : tasks.value.filter(task => task.status === filter.value));
const activeCount = computed(() => tasks.value.filter(task => ['uploading', 'inspecting', 'awaiting_confirmation', 'queued', 'running', 'cancel_requested'].includes(task.status)).length);
const isActive = (task: DatabaseTransferTask) => ['uploading', 'inspecting', 'awaiting_confirmation', 'queued', 'running', 'cancel_requested'].includes(task.status);
let socket: WebSocket | null = null;
let reconnectTimer = 0;
let pollTimer = 0;
let mounted = false;
const notified = new Set<string>();

function onOpenRequest() { emit('update:open', true); }
async function onExportRequest(event: Event) {
  emit('update:open', true);
  const detail = (event as CustomEvent<Record<string, unknown>>).detail || {};
  const relational = detail.scope === 'table' || detail.scope === 'database';
  const payload = { ...detail, direction: 'export', format: relational ? 'sql' : detail.format, scope: detail.scope === 'table' ? 'table' : detail.scope === 'database' ? 'database' : detail.scope };
  try { acceptSocketTask(await createDatabaseTransfer(payload)); await refresh(); }
  catch (error) { ElMessage.error(errorMessage(error)); }
}
async function onUploadRequest(event: Event) {
  emit('update:open', true);
  const detail = (event as CustomEvent<{ file: File; target: Record<string, unknown> }>).detail;
  if (!detail?.file) return;
  try { await uploadFile(detail.file, detail.target); await refresh(); }
  catch (error) { ElMessage.error(errorMessage(error)); }
}

function merge(items: DatabaseTransferTask[]) {
  const previous = new Map(tasks.value.map(task => [task.id, task.status]));
  tasks.value = items;
  for (const task of items) notifyCompletion(task, previous.get(task.id));
}
function notifyCompletion(task: DatabaseTransferTask, previous?: string) {
  if (task.status === 'succeeded' && previous && !['succeeded', 'expired'].includes(previous) && !notified.has(task.id)) {
    notified.add(task.id);
    window.dispatchEvent(new CustomEvent('database-transfer:completed', { detail: task }));
    ElNotification({ title: '导入导出已完成', message: `${task.assetName || task.scope} · ${task.scope}`, type: 'success' });
  }
}
async function refresh(silent = false) {
  loading.value = true;
  try { merge(await listDatabaseTransferTasks()); }
  catch (error) { if (!silent) ElMessage.error(errorMessage(error)); }
  finally { loading.value = false; }
}
function acceptSocketTask(task: DatabaseTransferTask) {
  const old = tasks.value.find(item => item.id === task.id)?.status;
  const next = [...tasks.value.filter(item => item.id !== task.id), task].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  tasks.value = next;
  notifyCompletion(task, old);
}
function connectSocket() {
  if (!mounted || socket) return;
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  socket = new WebSocket(`${protocol}//${location.host}/ws/database-transfers/`);
  socket.onmessage = event => { try { acceptSocketTask(JSON.parse(event.data) as DatabaseTransferTask); } catch { /* Ignore malformed events and recover through polling. */ } };
  socket.onclose = () => { socket = null; if (mounted) reconnectTimer = window.setTimeout(connectSocket, 2000); };
  socket.onerror = () => socket?.close();
}
function closeSocket() { if (reconnectTimer) clearTimeout(reconnectTimer); reconnectTimer = 0; socket?.close(); socket = null; }
watch(() => props.open, open => { if (open) void refresh(); });
onMounted(() => {
  mounted = true;
  window.addEventListener('database-transfer:open', onOpenRequest);
  window.addEventListener('database-transfer:export', onExportRequest);
  window.addEventListener('database-transfer:upload', onUploadRequest);
  void refresh(true);
  connectSocket();
  pollTimer = window.setInterval(() => { void refresh(true); }, 5000);
});
onUnmounted(() => {
  mounted = false; closeSocket(); if (pollTimer) clearInterval(pollTimer);
  window.removeEventListener('database-transfer:open', onOpenRequest);
  window.removeEventListener('database-transfer:export', onExportRequest);
  window.removeEventListener('database-transfer:upload', onUploadRequest);
});

async function uploadFile(file: File, target: Record<string, unknown>) {
  const size = 8 * 1024 * 1024;
  const count = Math.max(1, Math.ceil(file.size / size));
  const task = await beginDatabaseTransferUpload({ ...target, fileName: file.name, chunks: count, totalBytes: file.size });
  acceptSocketTask(task);
  for (let index = 0; index < count; index++) {
    const chunk = file.slice(index * size, Math.min(file.size, (index + 1) * size));
    for (let attempt = 0; ; attempt++) {
      try { await uploadDatabaseTransferChunk(task.id, index, chunk); break; }
      catch (error) { if (attempt >= 2) throw error; }
    }
    acceptSocketTask({ ...task, processedBytes: Math.min(file.size, (index + 1) * size), progress: Math.floor((index + 1) * 100 / count) });
  }
  // The server computes SHA-256 while streaming the uploaded chunks.
  acceptSocketTask(await completeDatabaseTransferUpload(task.id, count, ''));
}
async function confirm(task: DatabaseTransferTask) {
  const chosen = policy.value[task.id] || 'append';
  const destructive = ['overwrite', 'skip'].includes(chosen);
  const affected = previewObjects(task).filter(item => item.exists).map(item => item.name);
  const affectedText = affected.length ? `受影响的已有表 (${affected.length})：${affected.slice(0, 20).join('、')}${affected.length > 20 ? '…（完整列表见预检）' : ''}。` : '';
  try {
    if (destructive || task.format === 'sql') await ElMessageBox.confirm(chosen === 'overwrite' && ['table', 'database'].includes(task.scope) ? `${affectedText}将覆盖文件涉及的目标表。有结构定义时删除重建，仅数据时清空数据，操作不可逆。MySQL DDL 无法保证回滚，确定继续？` : `将按“${chosen === 'skip' ? '跳过已有表' : '追加'}”策略导入，继续吗？`, '确认导入策略', { type: 'warning' });
    acceptSocketTask(await confirmDatabaseTransfer(task.id, chosen, destructive || task.format === 'sql'));
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error)); }
}
async function cancel(task: DatabaseTransferTask) { try { acceptSocketTask(await cancelDatabaseTransfer(task.id)); } catch (error) { ElMessage.error(errorMessage(error)); } }
async function retry(task: DatabaseTransferTask) {
  try {
    const confirmed = task.direction !== 'import' || task.format !== 'sql' || await ElMessageBox.confirm('已完成表会跳过；未完成表仍可能有已提交的 DDL 或非事务数据，重复追加可能冲突。请核对后确认重试。', '重试 SQL 导入', { type: 'warning' }).then(() => true).catch(() => false);
    if (!confirmed) return;
    acceptSocketTask(await retryDatabaseTransfer(task.id, confirmed));
  } catch (error) { ElMessage.error(errorMessage(error)); }
}
async function remove(task: DatabaseTransferTask) { try { await deleteDatabaseTransfer(task.id); tasks.value = tasks.value.filter(item => item.id !== task.id); } catch (error) { ElMessage.error(errorMessage(error)); } }
async function download(task: DatabaseTransferTask) {
  const anchor = document.createElement('a');
  anchor.href = databaseTransferDownloadUrl(task.id);
  anchor.download = task.sourceName || `transfer-${task.id}.${task.format}`;
  anchor.click();
}
function previewObjects(task: DatabaseTransferTask) {
  return (task.preview.objects || []) as { name: string; exists: boolean; hasStructure: boolean; rows: number }[];
}
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 ** 2).toFixed(1)} MB`; }
function stageLabel(task: DatabaseTransferTask) {
  const labels: Record<string, string> = { uploading: '分片上传', inspection_queued: '等待预检', inspection_running: '预检中', validating_sql: '校验 SQL', awaiting_confirmation: '等待确认', queued: '等待执行', starting: '开始执行', complete: '完成', failed: '失败', cancelled: '取消', timeout: '超时' };
  if (task.stage.startsWith('exporting_table:')) return `导出表：${task.stage.slice(16)}`;
  if (task.stage.startsWith('importing_table:')) return `导入表：${task.stage.slice(16)}`;
  return labels[task.stage] || task.stage || statusLabel(task.status);
}
function elapsed(task: DatabaseTransferTask) {
  const seconds = Math.max(0, Math.floor(((task.finishedAt ? Date.parse(task.finishedAt) : Date.now()) - Date.parse(task.startedAt || task.createdAt)) / 1000));
  return `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
}
function statusLabel(value: string) { return ({ uploading: '上传中', inspecting: '预检中', awaiting_confirmation: '待确认', queued: '排队中', running: '执行中', cancel_requested: '正在取消', cancelled: '已取消', succeeded: '已完成', failed: '失败', expired: '已过期' } as Record<string, string>)[value] || value; }
</script>

<template>
  <el-popover v-model:visible="popoverVisible" placement="bottom-end" :width="440" trigger="click" popper-class="database-transfer-message-popover">
    <template #reference>
      <el-button class="workspace-icon-button transfer-message-button" circle title="任务消息" aria-label="任务消息">
        <Bell :size="18" />
        <span v-if="activeCount" class="transfer-message-badge">{{ activeCount > 99 ? '99+' : activeCount }}</span>
      </el-button>
    </template>
    <section class="transfer-message-panel" aria-label="导入导出任务消息">
      <header class="transfer-message-header">
        <div><strong>消息</strong><span>导入导出任务</span></div>
        <span>{{ activeCount }} 项进行中</span>
      </header>
      <div class="transfer-toolbar">
        <el-select v-model="filter" aria-label="任务状态筛选">
          <el-option label="全部任务" value="all"/><el-option label="执行中" value="running"/><el-option label="待确认" value="awaiting_confirmation"/><el-option label="已完成" value="succeeded"/><el-option label="失败" value="failed"/><el-option label="已取消" value="cancelled"/>
        </el-select>
        <el-button :icon="RefreshCw" :loading="loading" title="刷新任务" aria-label="刷新任务" @click="refresh"/>
      </div>
      <el-scrollbar v-loading="loading" class="transfer-list">
        <el-empty v-if="!visibleTasks.length" description="暂无导入导出任务"/>
        <article v-for="task in visibleTasks" :key="task.id" class="transfer-task">
          <header><div><strong>{{ task.direction === 'export' ? '导出' : '导入' }} · {{ task.assetName || task.scope }}<template v-if="task.database"> / {{ task.database }}</template><template v-if="task.objectName"> / {{ task.objectName }}</template></strong><span>{{ task.sourceName || `${task.scope}.${task.format}` }}</span></div><el-tag size="small" :type="task.status === 'failed' ? 'danger' : task.status === 'succeeded' ? 'success' : isActive(task) ? 'primary' : 'info'">{{ statusLabel(task.status) }}</el-tag></header>
          <el-progress v-if="isActive(task) && task.status !== 'awaiting_confirmation'" :percentage="task.progress" :status="task.status === 'cancel_requested' ? 'warning' : undefined"/>
          <div class="transfer-stage"><span>{{ stageLabel(task) }} · {{ elapsed(task) }}</span><span>{{ task.processedRows.toLocaleString() }} 行 · {{ formatBytes(task.processedBytes) }}<template v-if="task.totalBytes"> / {{ formatBytes(task.totalBytes) }}</template></span></div>
          <div v-if="task.status === 'awaiting_confirmation'" class="transfer-preview"><div v-if="previewObjects(task).length" class="transfer-table-preview"><p v-for="item in previewObjects(task)" :key="item.name"><strong>{{ item.name }}</strong> · {{ item.exists ? '目标已存在' : '新表' }} · {{ item.hasStructure ? '包含结构' : '仅数据' }} · {{ item.rows.toLocaleString() }} 行</p><p v-for="(warning, index) in task.preview.warnings" :key="index" class="transfer-warning">{{ warning }}</p></div><pre v-else>{{ JSON.stringify(task.preview, null, 2) }}</pre><el-select v-model="policy[task.id]" aria-label="冲突处理策略"><el-option label="追加，冲突时报错" value="append"/><el-option label="覆盖目标数据" value="overwrite"/><el-option label="跳过冲突对象" value="skip"/><el-option v-if="task.scope === 'queries' || task.scope === 'connections'" label="同名自动重命名" value="rename"/></el-select><el-button type="primary" :loading="confirming === task.id" @click="confirming = task.id; confirm(task).finally(() => confirming = '')">确认执行</el-button></div>
          <p v-if="task.error" class="transfer-error">{{ task.error }}</p>
          <template v-if="task.status !== 'awaiting_confirmation'"><p v-for="(warning, index) in task.preview.warnings" :key="index" class="transfer-warning">{{ warning }}</p></template>
          <p v-if="task.checkpoints?.completedTables?.length" class="transfer-checkpoint">已完成表：{{ task.checkpoints.completedTables.join('、') }}</p>
          <p v-if="task.checkpoints?.ddlMayBeCommitted" class="transfer-error">{{ task.checkpoints.currentTable }} 的结构变更可能已提交，失败或取消不能自动恢复。</p>
          <footer><small>{{ new Date(task.createdAt).toLocaleString() }} · 保留至 {{ new Date(task.expiresAt).toLocaleDateString() }}</small><div><el-button v-if="task.canDownload" text type="primary" @click="download(task)"><Download :size="15"/>下载</el-button><el-button v-if="isActive(task)" text type="warning" @click="cancel(task)"><X :size="15"/>取消</el-button><el-button v-if="['failed','cancelled'].includes(task.status)" text @click="retry(task)"><RefreshCw :size="15"/>重试</el-button><el-button v-if="!isActive(task)" text type="danger" @click="remove(task)"><Trash2 :size="15"/>删除</el-button></div></footer>
        </article>
      </el-scrollbar>
    </section>
  </el-popover>
</template>

<style scoped>
.transfer-table-preview{flex-basis:100%;max-height:200px;overflow:auto;font-size:12px;overflow-wrap:anywhere}.transfer-warning{color:var(--el-color-warning)}.transfer-checkpoint{font-size:12px;overflow-wrap:anywhere}.transfer-toolbar{grid-template-columns:minmax(0,1fr) 32px!important}
.transfer-message-button{position:relative}.transfer-message-badge{position:absolute;top:-5px;right:-6px;display:grid;place-items:center;min-width:17px;height:17px;padding:0 4px;border:2px solid var(--workspace-surface);border-radius:9px;background:var(--el-color-danger);color:#fff;font-size:10px;font-weight:700;line-height:1}.transfer-message-panel{min-width:0}.transfer-message-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:2px 2px 12px;border-bottom:1px solid var(--el-border-color-lighter)}.transfer-message-header>div{display:grid;gap:2px}.transfer-message-header strong{font-size:16px}.transfer-message-header span{color:var(--el-text-color-secondary);font-size:12px}.transfer-toolbar{display:grid;grid-template-columns:minmax(0,1fr) 32px auto;align-items:center;gap:8px;padding:12px 0}.transfer-list{height:min(560px,calc(100vh - 170px))}.transfer-task{padding:13px 2px;border-bottom:1px solid var(--el-border-color-lighter)}.transfer-task:last-child{border-bottom:0}.transfer-task header,.transfer-task footer,.transfer-stage{display:flex;align-items:center;justify-content:space-between;gap:10px}.transfer-task header>div{display:grid;gap:4px;min-width:0}.transfer-task header strong,.transfer-task header span{overflow-wrap:anywhere}.transfer-task header span,.transfer-stage,.transfer-task footer small{color:var(--el-text-color-secondary);font-size:12px}.transfer-task :deep(.el-progress){margin-top:9px}.transfer-stage{margin-top:7px}.transfer-preview{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:10px}.transfer-preview pre{flex-basis:100%;max-height:150px;overflow:auto;margin:0;padding:10px;background:var(--el-fill-color-light);font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}.transfer-error{color:var(--el-color-danger);overflow-wrap:anywhere}.transfer-task footer{align-items:flex-start;margin-top:8px}.transfer-task footer small{padding-top:7px}.transfer-task footer>div{display:flex;flex-wrap:wrap;justify-content:flex-end}.transfer-task footer :deep(.el-button){margin-left:4px;padding-inline:4px}:global(.database-transfer-message-popover.el-popover){max-width:calc(100vw - 24px);padding:12px}@media(max-width:540px){.transfer-list{height:calc(100vh - 190px)}.transfer-task footer{flex-direction:column}.transfer-task footer>div{justify-content:flex-start}.transfer-toolbar{grid-template-columns:minmax(0,1fr) 32px}.transfer-toolbar>.el-button:last-child{grid-column:1/-1}.transfer-message-header>span{display:none}}
</style>
