<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { errorMessage } from '@shared/utils/errors';
import { getDatabaseTableData, runDatabaseObjectAction, type TableReference } from '../api/databaseManagement';
const props = defineProps<{ target: TableReference; action: 'drop' | 'delete_rows' | 'truncate' }>();
const emit = defineEmits<{ close: []; saved: [] }>();
const titles = { drop: '删除表', delete_rows: '删除数据', truncate: '截断表' };
const name = ref('');
const confirmed = ref(false);
const count = ref<number | null>(null);
const busy = ref(false);
const failure = ref('');
const valid = computed(() => confirmed.value && (props.action !== 'drop' || name.value === props.target.table));
async function execute() {
  if (!valid.value || busy.value) return;
  busy.value = true; failure.value = '';
  try { await runDatabaseObjectAction(props.target.assetId, { ...props.target, name: props.target.table, objectType: 'table', action: props.action, confirmed: true, confirmName: name.value }); emit('saved'); emit('close'); }
  catch (error) { failure.value = errorMessage(error); }
  finally { busy.value = false; }
}
onMounted(async () => { try { count.value = (await getDatabaseTableData(props.target.assetId, { ...props.target, page: 1, pageSize: 1 })).total; } catch { count.value = null; } });
</script>
<template>
  <el-dialog :model-value="true" :title="titles[action]" width="min(540px,94vw)" align-center :close-on-click-modal="false" :show-close="!busy" @close="emit('close')"><el-alert type="warning" :closable="false" :title="action === 'drop' ? '将永久删除此表的结构和全部数据' : action === 'truncate' ? '将清空全部数据并重置自增值，MySQL 截断操作无法回滚' : '将删除此表的全部数据，保留表结构'" /><p>{{ target.database }} / {{ target.table }}</p><p>影响范围：当前表全部数据（{{ count === null ? '行数未知' : `${count.toLocaleString()} 行` }}）</p><el-form v-if="action === 'drop'" label-position="top"><el-form-item :label="`输入表名 ${target.table} 确认`" required><el-input v-model="name" autocomplete="off" /></el-form-item></el-form><el-checkbox v-model="confirmed">已确认影响范围，执行后无法从此界面恢复</el-checkbox><el-alert v-if="failure" :title="failure" type="error" :closable="false" /><template #footer><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button type="danger" :disabled="!valid" :loading="busy" @click="execute">确认{{ titles[action] }}</el-button></template></el-dialog>
</template>
<style scoped>p{overflow-wrap:anywhere}.el-form{margin-top:16px}:deep(.el-checkbox){height:auto;max-width:100%}:deep(.el-checkbox__label){white-space:normal}</style>
