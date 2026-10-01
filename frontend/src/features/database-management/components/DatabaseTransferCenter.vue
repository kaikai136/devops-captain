<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus';
import { Download, RefreshCw, Trash2, Upload, X } from '@lucide/vue';
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
const visibleTasks = computed(() => filter.value === 'all' ? tasks.value : tasks.value.filter(task => task.status === filter.value));
const activeCount = computed(() => tasks.value.filter(task => ['uploading', 'inspecting', 'awaiting_confirmation', 'queued', 'running', 'cancel_requested'].includes(task.status)).length);
const isActive = (task: DatabaseTransferTask) => ['uploading', 'inspecting', 'awaiting_confirmation', 'queued', 'running', 'cancel_requested'].includes(task.status);
let socket: WebSocket | null = null;
let reconnectTimer = 0;
let pollTimer = 0;
let mounted = true;
const notified = new Set<string>();

function onOpenRequest() { emit('update:open', true); }
async function onExportRequest(event: Event) {
  emit('update:open', true);
  try { acceptSocketTask(await createDatabaseTransfer((event as CustomEvent<Record<string, unknown>>).detail)); await refresh(); }
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
    ElNotification({ title: '导入导出已完成', message: `${task.assetName || task.scope} · ${task.scope}`, type: 'success' });
  }
}
async function refresh() {
  loading.value = true;
  try { merge(await listDatabaseTransferTasks()); }
  catch (error) { ElMessage.error(errorMessage(error)); }
  finally { loading.value = false; }
}
function acceptSocketTask(task: DatabaseTransferTask) {
  const old = tasks.value.find(item => item.id === task.id)?.status;
  const next = [...tasks.value.filter(item => item.id !== task.id), task].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  tasks.value = next;
  notifyCompletion(task, old);
}
function connectSocket() {
  if (!mounted || !props.open || socket) return;
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  socket = new WebSocket(`${protocol}//${location.host}/ws/database-transfers/`);
  socket.onmessage = event => { try { acceptSocketTask(JSON.parse(event.data) as DatabaseTransferTask); } catch { /* Ignore malformed events and recover through polling. */ } };
  socket.onclose = () => { socket = null; if (mounted && props.open) reconnectTimer = window.setTimeout(connectSocket, 2000); };
  socket.onerror = () => socket?.close();
}
function closeSocket() { if (reconnectTimer) clearTimeout(reconnectTimer); reconnectTimer = 0; socket?.close(); socket = null; }
watch(() => props.open, async open => {
  if (open) { await refresh(); connectSocket(); pollTimer = window.setInterval(() => { void refresh(); }, 5000); }
  else { closeSocket(); if (pollTimer) clearInterval(pollTimer); pollTimer = 0; }
}, { immediate: true });
onMounted(() => {
  mounted = true;
  window.addEventListener('database-transfer:open', onOpenRequest);
  window.addEventListener('database-transfer:export', onExportRequest);
  window.addEventListener('database-transfer:upload', onUploadRequest);
  if (props.open) connectSocket();
});
onUnmounted(() => {
  mounted = false; closeSocket(); if (pollTimer) clearInterval(pollTimer);
  window.removeEventListener('database-transfer:open', onOpenRequest);
  window.removeEventListener('database-transfer:export', onExportRequest);
  window.removeEventListener('database-transfer:upload', onUploadRequest);
});

async function digest(file: File) {
  const hash = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('');
}
async function uploadFile(file: File, target: Record<string, unknown>) {
  const size = 8 * 1024 * 1024;
  const count = Math.max(1, Math.ceil(file.size / size));
  const task = await beginDatabaseTransferUpload({ ...target, fileName: file.name, chunks: count, totalBytes: file.size });
  acceptSocketTask(task);
  for (let index = 0; index < count; index++) await uploadDatabaseTransferChunk(task.id, index, file.slice(index * size, Math.min(file.size, (index + 1) * size)));
  acceptSocketTask(await completeDatabaseTransferUpload(task.id, count, await digest(file)));
}
async function chooseImport() {
  const scope = window.prompt('导入范围：table / database / redis / queries / connections', 'table');
  if (!scope) return;
  const assetIdText = window.prompt('目标数据库资产 ID', '');
  if (!assetIdText || !/^\d+$/.test(assetIdText)) return;
  const database = window.prompt('目标数据库名称（Redis 填 DB 编号）', '');
  if (database === null) return;
  const file = document.createElement('input'); file.type = 'file';
  file.accept = scope === 'database' ? '.zip,.json' : scope === 'redis' ? '.json,.csv' : '.csv,.sql,.json,.zip';
  file.onchange = async () => {
    const selected = file.files?.[0]; if (!selected) return;
    const format = selected.name.split('.').pop()?.toLowerCase() || 'json';
    try { await uploadFile(selected, { scope, format, assetId: Number(assetIdText), database, objectName: scope === 'table' ? window.prompt('目标表名', '') || '' : '' }); await refresh(); }
    catch (error) { ElMessage.error(errorMessage(error)); }
  };
  file.click();
}
async function confirm(task: DatabaseTransferTask) {
  const chosen = policy.value[task.id] || 'append';
  const destructive = ['overwrite', 'skip'].includes(chosen);
  try {
    if (destructive) await ElMessageBox.confirm(`将按“${chosen === 'overwrite' ? '覆盖' : '跳过冲突'}”策略处理数据，继续吗？`, '确认导入策略', { type: 'warning' });
    acceptSocketTask(await confirmDatabaseTransfer(task.id, chosen, destructive));
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error)); }
}
async function cancel(task: DatabaseTransferTask) { try { acceptSocketTask(await cancelDatabaseTransfer(task.id)); } catch (error) { ElMessage.error(errorMessage(error)); } }
async function retry(task: DatabaseTransferTask) {
  try {
    const confirmed = task.format !== 'sql' || await ElMessageBox.confirm('SQL 重试可能重复执行已成功的语句，确定继续？', '重试 SQL 导入', { type: 'warning' }).then(() => true).catch(() => false);
    if (!confirmed) return;
    acceptSocketTask(await retryDatabaseTransfer(task.id, confirmed));
  } catch (error) { ElMessage.error(errorMessage(error)); }
}
async function remove(task: DatabaseTransferTask) { try { await deleteDatabaseTransfer(task.id); tasks.value = tasks.value.filter(item => item.id !== task.id); } catch (error) { ElMessage.error(errorMessage(error)); } }
async function download(task: DatabaseTransferTask) {
  try {
    const response = await fetch(databaseTransferDownloadUrl(task.id), { credentials: 'include' });
    if (!response.ok) throw new Error((await response.json()).error || '下载失败');
    const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement('a'); anchor.href = url; anchor.download = task.sourceName || `transfer-${task.id}.${task.format}`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { ElMessage.error(errorMessage(error)); }
}
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 ** 2).toFixed(1)} MB`; }
function statusLabel(value: string) { return ({ uploading: '上传中', inspecting: '预检中', awaiting_confirmation: '待确认', queued: '排队中', running: '执行中', cancel_requested: '正在取消', cancelled: '已取消', succeeded: '已完成', failed: '失败', expired: '已过期' } as Record<string, string>)[value] || value; }
</script>

<template>
  <el-drawer :model-value="open" title="导入导出任务" size="min(760px, 96vw)" :close-on-click-modal="false" @update:model-value="emit('update:open', $event)">
    <div class="transfer-toolbar"><el-select v-model="filter" aria-label="任务状态筛选" style="width:160px"><el-option label="全部任务" value="all"/><el-option label="执行中" value="running"/><el-option label="待确认" value="awaiting_confirmation"/><el-option label="已完成" value="succeeded"/><el-option label="失败" value="failed"/><el-option label="已取消" value="cancelled"/></el-select><el-button :icon="RefreshCw" :loading="loading" title="刷新任务" aria-label="刷新任务" @click="refresh"/><el-button type="primary" :icon="Upload" @click="chooseImport">导入文件</el-button><span class="transfer-count">{{ activeCount }} 项进行中</span></div>
    <el-scrollbar v-loading="loading" class="transfer-list">
      <el-empty v-if="!visibleTasks.length" description="暂无导入导出任务"/>
      <article v-for="task in visibleTasks" :key="task.id" class="transfer-task">
        <header><div><strong>{{ task.direction === 'export' ? '导出' : '导入' }} · {{ task.assetName || task.scope }}<template v-if="task.database"> / {{ task.database }}</template><template v-if="task.objectName"> / {{ task.objectName }}</template></strong><span>{{ task.sourceName || `${task.scope}.${task.format}` }}</span></div><el-tag :type="task.status === 'failed' ? 'danger' : task.status === 'succeeded' ? 'success' : isActive(task) ? 'primary' : 'info'">{{ statusLabel(task.status) }}</el-tag></header>
        <el-progress v-if="isActive(task) && task.status !== 'awaiting_confirmation'" :percentage="task.progress" :status="task.status === 'cancel_requested' ? 'warning' : undefined"/>
        <div class="transfer-stage"><span>{{ task.stage || statusLabel(task.status) }}</span><span>{{ task.processedRows.toLocaleString() }} 行 · {{ formatBytes(task.processedBytes) }}<template v-if="task.totalBytes"> / {{ formatBytes(task.totalBytes) }}</template></span></div>
        <div v-if="task.status === 'awaiting_confirmation'" class="transfer-preview"><pre>{{ JSON.stringify(task.preview, null, 2) }}</pre><el-select v-model="policy[task.id]" aria-label="冲突处理策略"><el-option label="追加，冲突时报错" value="append"/><el-option label="覆盖目标数据" value="overwrite"/><el-option label="跳过冲突对象" value="skip"/><el-option v-if="task.scope === 'queries' || task.scope === 'connections'" label="同名自动重命名" value="rename"/></el-select><el-button type="primary" :loading="confirming === task.id" @click="confirming = task.id; confirm(task).finally(() => confirming = '')">确认执行</el-button></div>
        <p v-if="task.error" class="transfer-error">{{ task.error }}</p>
        <footer><small>{{ new Date(task.createdAt).toLocaleString() }} · 保留至 {{ new Date(task.expiresAt).toLocaleDateString() }}</small><div><el-button v-if="task.canDownload" text type="primary" @click="download(task)"><Download :size="15"/>下载</el-button><el-button v-if="isActive(task)" text type="warning" @click="cancel(task)"><X :size="15"/>取消</el-button><el-button v-if="['failed','cancelled'].includes(task.status)" text @click="retry(task)"><RefreshCw :size="15"/>重试</el-button><el-button v-if="!isActive(task)" text type="danger" @click="remove(task)"><Trash2 :size="15"/>删除</el-button></div></footer>
      </article>
    </el-scrollbar>
  </el-drawer>
</template>

<style scoped>
.transfer-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:14px}.transfer-count{margin-left:auto;color:var(--el-text-color-secondary)}.transfer-list{height:calc(100vh - 150px)}.transfer-task{padding:14px 0;border-bottom:1px solid var(--el-border-color-lighter)}.transfer-task header,.transfer-task footer,.transfer-stage{display:flex;align-items:center;justify-content:space-between;gap:12px}.transfer-task header>div{display:grid;gap:5px;min-width:0}.transfer-task header strong,.transfer-task header span{overflow-wrap:anywhere}.transfer-task header span,.transfer-stage,.transfer-task footer small{color:var(--el-text-color-secondary);font-size:12px}.transfer-stage{margin-top:8px}.transfer-preview{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:10px}.transfer-preview pre{flex-basis:100%;max-height:180px;overflow:auto;margin:0;padding:10px;background:var(--el-fill-color-light);font-size:12px}.transfer-error{color:var(--el-color-danger);overflow-wrap:anywhere}.transfer-task footer{margin-top:8px}.transfer-task footer>div{display:flex;flex-wrap:wrap}@media(max-width:540px){.transfer-toolbar{flex-wrap:wrap}.transfer-count{margin-left:0}.transfer-task footer{align-items:flex-start;flex-direction:column}}
</style>
