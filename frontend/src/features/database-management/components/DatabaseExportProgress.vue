<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { errorMessage } from '@shared/utils/errors';
import { createDatabaseTransfer, cancelDatabaseTransfer, databaseTransferDownloadUrl, type DatabaseTransferTask } from '../api/databaseManagement';
import { chooseExportDestination, saveExport, type ExportDestination, type SavedExportFile } from '../utils/exportDestination';

type Checkpoints = { currentTable?: string; completedSteps?: number; totalSteps?: number; tableRows?: number; tableTotal?: number; completedTables?: string[]; failedTables?: string[]; logs?: { time: string; level: string; message: string }[] };
type Session = { task: DatabaseTransferTask | null; destination?: ExportDestination; state: 'creating' | 'running' | 'saving' | 'saved' | 'ready' | 'error' | 'cancelled'; error: string; file: string; savedFiles?: SavedExportFile[]; controller?: AbortController };
const props = defineProps<{ tasks: DatabaseTransferTask[] }>();
const sessions = shallowRef<Session[]>([]);
const active = shallowRef<Session | null>(null);
const open = ref(false);
const now = ref(Date.now());
const task = computed(() => active.value?.task);
const checkpoints = computed(() => (task.value?.checkpoints || {}) as Checkpoints);
const busy = computed(() => active.value && ['creating', 'running', 'saving'].includes(active.value.state));
const elapsed = computed(() => {
  const started = task.value?.startedAt || task.value?.createdAt;
  return started ? Math.max(0, Math.floor(((task.value?.finishedAt && active.value?.state !== 'saving' ? Date.parse(task.value.finishedAt) : now.value) - Date.parse(started)) / 1000)) : 0;
});
const heading = computed(() => {
  if (!active.value) return '';
  if (active.value.state === 'saving') return `正在保存到本地：${active.value.file}`;
  if (active.value.state === 'ready') return '导出已就绪，请选择本地位置保存文件';
  if (active.value.state === 'saved') return active.value.destination?.kind === 'download' ? '已交给浏览器下载，请检查下载列表' : checkpoints.value.failedTables?.length ? '已保存，部分表导出失败' : '导出完成，文件已保存到本地';
  if (active.value.state === 'error') return '导出或本地保存失败';
  if (active.value.state === 'cancelled') return '任务已取消';
  return task.value?.stage === 'packaging' ? '正在生成文件' : checkpoints.value.currentTable ? `正在导出：${checkpoints.value.currentTable}` : '正在排队';
});
let timer = 0;
function select(session: Session) { active.value = session; open.value = true; }
function selectById(id: string) {
  const session = sessions.value.find(item => item.task?.id === id);
  if (session) select(session);
}
function updateSession(session: Session, changes: Partial<Session>) {
  const wasActive = active.value === session || Boolean(session.task && active.value?.task?.id === session.task.id);
  Object.assign(session, changes);
  sessions.value = [...sessions.value];
  if (wasActive) active.value = { ...session };
}
async function save(session: Session) {
  if (!session.task || !session.destination || ['saving', 'saved'].includes(session.state)) return;
  const controller = new AbortController();
  updateSession(session, { state: 'saving', error: '', savedFiles: [], controller });
  try {
    if (session.destination.kind === 'download') {
      const link = document.createElement('a');
      link.href = databaseTransferDownloadUrl(session.task.id);
      link.download = session.destination.name;
      link.click();
      updateSession(session, { state: 'saved', controller: undefined });
      return;
    }
    const response = await fetch(databaseTransferDownloadUrl(session.task.id), { credentials: 'include', signal: controller.signal });
    const savedFiles = await saveExport(response, session.destination, file => updateSession(session, { file }), controller.signal);
    if (!savedFiles.length) throw new Error('没有文件写入本地，请重新保存');
    updateSession(session, { state: 'saved', savedFiles, controller: undefined });
  } catch (error) { updateSession(session, { state: 'error', error: errorMessage(error), controller: undefined }); }
}
function refresh() {
  now.value = Date.now();
  const tasks = props.tasks;
  for (const session of sessions.value) {
    if (session.state !== 'running') continue;
    const next = tasks.find(item => item.id === session.task?.id);
    if (!next) continue;
    updateSession(session, { task: next });
    if (next.status === 'succeeded') { if (session.destination) void save(session); else updateSession(session, { state: 'ready' }); }
    else if (['failed', 'expired', 'cancelled'].includes(next.status)) updateSession(session, { state: next.status === 'cancelled' ? 'cancelled' : 'error', error: next.error });
  }
}
watch(() => props.tasks, refresh);
async function start(event: Event) {
  const detail = (event as CustomEvent<{ payload: Record<string, unknown>; destination: ExportDestination }>).detail;
  if (!detail?.payload || !detail.destination) return;
  const session: Session = { task: null, destination: detail.destination, state: 'creating', error: '', file: '' };
  sessions.value = [session, ...sessions.value]; select(session);
  try {
    const created = await createDatabaseTransfer(detail.payload);
    updateSession(session, { task: created, state: 'running' });
    await refresh();
  } catch (error) { updateSession(session, { state: 'error', error: errorMessage(error) }); }
}
function liveSession() { return sessions.value.find(session => session.task?.id === task.value?.id) || active.value; }
async function cancel() {
  const session = liveSession();
  if (!session) return;
  if (session.state === 'saving') { session.controller?.abort(); return; }
  if (session.task) {
    try { updateSession(session, { task: await cancelDatabaseTransfer(session.task.id) }); }
    catch (error) { ElMessage.error(errorMessage(error)); }
  }
}
async function retrySave() {
  const session = liveSession();
  if (!session?.task) return;
  try {
    const destination = await chooseExportDestination(session.task.sourceName);
    updateSession(session, { destination, state: 'ready' });
    await save(session);
  } catch (error) { if ((error as DOMException).name !== 'AbortError') ElMessage.error(errorMessage(error)); }
}
function recover(event: Event) {
  const recovered = (event as CustomEvent<DatabaseTransferTask>).detail;
  if (!recovered) return;
  let session = sessions.value.find(item => item.task?.id === recovered.id);
  if (!session) {
    session = { task: recovered, state: recovered.status === 'succeeded' ? 'ready' : ['failed', 'expired', 'cancelled'].includes(recovered.status) ? 'error' : 'running', error: recovered.status === 'succeeded' ? '' : recovered.error, file: '' };
    sessions.value = [session, ...sessions.value];
  }
  select(session);
}
onMounted(() => {
  window.addEventListener('database-export:start', start);
  window.addEventListener('database-export:show', recover);
  timer = window.setInterval(refresh, 1000);
});
onUnmounted(() => {
  clearInterval(timer);
  for (const session of sessions.value) session.controller?.abort();
  window.removeEventListener('database-export:start', start);
  window.removeEventListener('database-export:show', recover);
});
</script>

<template>
  <el-dialog v-model="open" title="数据导出" width="min(620px, 94vw)" :close-on-click-modal="false">
    <section class="export-progress" aria-live="polite">
      <el-select v-if="sessions.length > 1" :model-value="task?.id" @change="selectById"><el-option v-for="item in sessions.filter(s => s.task)" :key="item.task!.id" :value="item.task!.id" :label="`${item.task!.database} · ${item.task!.format}`" /></el-select>
      <strong>{{ heading }}</strong>
      <div v-if="checkpoints.totalSteps" class="export-counts"><span>当前表：{{ checkpoints.tableRows || 0 }} / {{ checkpoints.tableTotal ?? '未知' }} 行</span><span>总进度：{{ checkpoints.completedSteps || 0 }} / {{ checkpoints.totalSteps }} 表</span></div>
      <p v-else-if="task?.status === 'succeeded'" class="export-destination">服务端已生成 {{ task.processedRows || 0 }} 行数据；此历史任务未记录表级进度。</p>
      <el-progress :percentage="task?.progress || 0" :status="active?.state === 'error' ? 'exception' : active?.state === 'saved' ? 'success' : undefined" />
      <p v-if="active?.destination" class="export-destination">保存位置：{{ active.destination.kind === 'download' ? '浏览器下载目录（ZIP）' : active.destination.kind === 'zip' ? active.destination.handle.name : active.destination.handle.name }}</p>
      <div class="export-log" role="log" aria-label="导出执行日志"><p v-for="(line, index) in checkpoints.logs || []" :key="index" :class="line.level"><time>{{ new Date(line.time).toLocaleTimeString() }}</time> {{ line.message }}</p><p v-if="!checkpoints.logs?.length">{{ task?.status === 'succeeded' ? '此历史任务没有导出日志。' : '等待任务开始…' }}</p><p v-for="file in active?.savedFiles || []" :key="file.name" class="success">已保存并校验：{{ file.name }}（{{ file.size }} 字节）</p></div>
      <el-alert v-if="active?.error" :title="active.error" type="error" :closable="false" />
      <p v-if="checkpoints.failedTables?.length" class="error">失败的表：{{ checkpoints.failedTables.join('、') }}</p>
      <p v-if="active?.state === 'saved'" class="success">{{ active.destination?.kind === 'download' ? '已触发 ZIP 下载。' : '文件已写入所选本地位置。' }}</p>
      <p class="export-elapsed">耗时：{{ elapsed }} 秒 · {{ task?.processedRows || 0 }} 行</p>
    </section>
    <template #footer><el-button v-if="task?.canDownload && active?.state !== 'saving'" @click="retrySave">另存到本地</el-button><el-button v-if="busy" :disabled="active?.state === 'creating' || task?.status === 'cancel_requested'" @click="cancel">{{ task?.status === 'cancel_requested' ? '正在取消' : '取消' }}</el-button><el-button @click="open = false">{{ busy ? '后台运行' : '关闭' }}</el-button></template>
  </el-dialog>
</template>

<style scoped>
.export-progress{display:grid;gap:12px;min-width:0}.export-progress>strong{overflow-wrap:anywhere}.export-counts{display:flex;justify-content:space-between;gap:12px;font-size:13px}.export-log{height:280px;overflow:auto;background:var(--el-fill-color-blank);border:1px solid var(--el-border-color-lighter);padding:10px;font:12px/1.7 monospace}.export-log p{margin:0;overflow-wrap:anywhere}.export-log time{color:var(--el-text-color-secondary)}.success{color:var(--el-color-success)}.error{color:var(--el-color-danger)}.warning{color:var(--el-color-warning)}.export-destination,.export-elapsed{margin:0;font-size:12px;color:var(--el-text-color-secondary)}
</style>
