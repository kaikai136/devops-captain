<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { errorMessage } from '@shared/utils/errors';
import { cancelDatabaseTransfer, confirmDatabaseTransfer, type DatabaseTransferTask } from '../api/databaseManagement';
const props = defineProps<{ tasks: DatabaseTransferTask[] }>();
const emit = defineEmits<{ updated: [task: DatabaseTransferTask] }>();
const taskId = ref('');
const opened = ref(false);
const busy = ref(false);
const confirmed = ref(false);
const policy = ref('append');
const task = computed(() => props.tasks.find(item => item.id === taskId.value));
const objects = computed(() => (task.value?.preview.objects || []) as { name: string; exists: boolean; rows: number; hasStructure: boolean; appendCompatible?: boolean }[]);
const canAppend = computed(() => objects.value.every(item => item.appendCompatible !== false));
const active = computed(() => task.value && ['uploading', 'inspecting', 'awaiting_confirmation', 'queued', 'running', 'cancel_requested'].includes(task.value.status));
const labels: Record<string, string> = { uploading: '上传中', inspecting: '预检中', awaiting_confirmation: '等待确认', queued: '排队中', running: '导入中', cancel_requested: '正在取消', succeeded: '导入完成', failed: '导入失败', cancelled: '已取消', expired: '已过期' };
function show(event: Event) { const detail = (event as CustomEvent<DatabaseTransferTask>).detail; if (detail?.direction !== 'import') return; taskId.value = detail.id; confirmed.value = false; policy.value = 'append'; opened.value = true; }
watch(canAppend, value => { if (!value) policy.value = 'skip'; });
async function confirm() {
  if (!task.value || busy.value || !confirmed.value || task.value.status !== 'awaiting_confirmation') return;
  busy.value = true;
  try { emit('updated', await confirmDatabaseTransfer(task.value.id, policy.value, true)); confirmed.value = false; }
  catch (error) { ElMessage.error(errorMessage(error)); }
  finally { busy.value = false; }
}
async function cancel() {
  if (!task.value || busy.value) return;
  busy.value = true;
  try { emit('updated', await cancelDatabaseTransfer(task.value.id)); }
  catch (error) { ElMessage.error(errorMessage(error)); }
  finally { busy.value = false; }
}
onMounted(() => window.addEventListener('database-import:show', show));
onUnmounted(() => window.removeEventListener('database-import:show', show));
</script>
<template>
  <el-dialog v-model="opened" title="SQL 导入进度与结果" width="min(820px,94vw)" :close-on-click-modal="false">
    <template v-if="task"><p><strong>{{ task.database }}</strong> · {{ task.sourceName }}</p><el-alert :title="labels[task.status] || task.status" :type="task.status === 'failed' ? 'error' : task.status === 'succeeded' ? 'success' : 'info'" :closable="false" /><el-progress :percentage="task.progress" /><p>当前阶段：{{ task.stage }} · {{ task.processedRows.toLocaleString() }} 行 · {{ task.processedBytes.toLocaleString() }} 字节</p>
      <template v-if="task.status === 'awaiting_confirmation'"><el-table :data="objects" max-height="260" border><el-table-column prop="name" label="表" /><el-table-column label="目标"><template #default="scope">{{ scope.row.exists ? '已存在' : '新表' }}</template></el-table-column><el-table-column prop="rows" label="行数" /><el-table-column label="内容"><template #default="scope">{{ scope.row.hasStructure ? '结构和数据' : '数据' }}</template></el-table-column></el-table><el-form label-position="top"><el-form-item label="目标表冲突处理"><el-select v-model="policy"><el-option label="追加数据" value="append" :disabled="!canAppend" /><el-option label="跳过已有表" value="skip" /><el-option label="覆盖（删除已有结构或数据）" value="overwrite" /></el-select></el-form-item><el-checkbox v-model="confirmed">我已核对目标数据库和冲突处理方式，确认执行导入</el-checkbox></el-form></template>
      <p v-for="(warning, i) in task.preview.warnings" :key="i" class="warning">{{ warning }}</p><p v-if="task.error" class="error">{{ task.error }}</p><p v-if="task.checkpoints?.completedTables?.length">已处理表：{{ task.checkpoints.completedTables.join('、') }}</p><p v-if="task.checkpoints?.failedTables?.length" class="error">失败表：{{ task.checkpoints.failedTables.join('、') }}</p><p v-if="task.checkpoints?.ddlMayBeCommitted" class="warning">部分结构变更可能已提交，取消或失败不会自动恢复。</p><div class="import-logs"><p v-for="(log, i) in task.checkpoints?.logs || []" :key="i" :class="{ error: log.level === 'error' }">{{ log.message }}</p></div>
    </template><template #footer><el-button v-if="active" type="danger" :disabled="busy || task?.status === 'cancel_requested'" @click="cancel">取消任务</el-button><el-button @click="opened = false">关闭</el-button><el-button v-if="task?.status === 'awaiting_confirmation'" type="primary" :disabled="!confirmed" :loading="busy" @click="confirm">确认执行</el-button></template>
  </el-dialog>
</template>
<style scoped>.warning{color:var(--el-color-warning)}.error{color:var(--el-color-danger)}p{overflow-wrap:anywhere}.el-form{margin-top:14px}.el-progress{margin-top:14px}.import-logs{max-height:180px;overflow:auto;font-size:12px}</style>
