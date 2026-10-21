<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { RefreshCw, Plus, Copy } from '@lucide/vue';
import { useAppContext } from '@app/context';
import { errorMessage } from '@shared/utils/errors';
import { connectionCan } from '../utils/mysqlConnection';
import { getDatabaseColumns, getDatabaseDdl, getDatabaseIndexes, modifyDatabaseSchema, type DatabaseAsset, type DatabaseColumn, type DatabaseIndex, type TableReference } from '../api/databaseManagement';
const props = defineProps<{ asset: DatabaseAsset; target: TableReference }>();
const emit = defineEmits<{ dirty: [value: boolean]; saved: [] }>();
const { canUsePageAction } = useAppContext();
const canEdit = () => canUsePageAction('databaseManagement', 'manage_schema') && connectionCan(props.asset, 'manage_schema');
const tab = ref('fields');
const columns = ref<DatabaseColumn[]>([]);
const indexes = ref<DatabaseIndex[]>([]);
const ddl = ref('');
const failure = ref('');
const loading = ref(false);
const saving = ref(false);
const action = ref('');
const form = ref({ name: '', newName: '', columnType: '', columns: [] as string[], unique: false });
watch(action, value => emit('dirty', Boolean(value)));
async function load() {
  loading.value = true; failure.value = '';
  const target = props.target;
  try {
    const [fields, keys, definition] = await Promise.all([getDatabaseColumns(target.assetId, target.database, target.table, target.schema), getDatabaseIndexes(target.assetId, target.database, target.table, target.schema), getDatabaseDdl(target.assetId, target.database, target.table, target.schema)]);
    columns.value = fields.columns; indexes.value = keys.indexes; ddl.value = definition.ddl;
  } catch (error) { failure.value = errorMessage(error); }
  finally { loading.value = false; }
}
function edit(kind: string, column?: DatabaseColumn) {
  if (!canEdit()) return;
  form.value = { name: column?.name || '', newName: column?.name || '', columnType: column?.type || 'VARCHAR(255)', columns: [], unique: false };
  action.value = kind;
}
async function save() {
  if (!canEdit() || saving.value || !form.value.name.trim()) return;
  saving.value = true;
  try { await modifyDatabaseSchema(props.target.assetId, { ...props.target, ...form.value, action: action.value }); action.value = ''; emit('saved'); await load(); }
  catch (error) { ElMessage.error(errorMessage(error)); }
  finally { saving.value = false; }
}
async function remove(kind: string, name: string) {
  if (!canEdit()) return;
  try { await ElMessageBox.confirm(`确认删除${kind === 'drop_column' ? '字段' : '索引'}“${name}”？MySQL 结构变更无法回滚。`, '删除结构', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }); await modifyDatabaseSchema(props.target.assetId, { ...props.target, action: kind, name }); emit('saved'); await load(); }
  catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error)); }
}
async function copy() { try { await navigator.clipboard.writeText(ddl.value); ElMessage.success('已复制完整 DDL'); } catch (error) { ElMessage.error(errorMessage(error)); } }
onMounted(load);
</script>
<template>
  <section class="structure-document" v-loading="loading">
    <header><strong>{{ target.table }} · 编辑结构</strong><el-button title="刷新" aria-label="刷新" @click="load"><RefreshCw :size="16" /></el-button><el-button v-if="tab !== 'ddl'" :disabled="!canEdit()" @click="edit(tab === 'fields' ? 'add_column' : 'create_index')"><Plus :size="16" />{{ tab === 'fields' ? '增加字段' : '增加索引' }}</el-button><el-button title="复制 DDL" aria-label="复制 DDL" @click="copy"><Copy :size="16" /></el-button></header>
    <el-alert v-if="failure" :title="failure" type="error" :closable="false" />
    <el-tabs v-model="tab" class="structure-tabs"><el-tab-pane label="字段" name="fields"><el-table :data="columns" height="100%" border><el-table-column prop="name" label="字段" min-width="160" /><el-table-column prop="type" label="类型" min-width="150" /><el-table-column prop="nullable" label="允许空值" width="100" /><el-table-column prop="column_key" label="键" width="80" /><el-table-column prop="default" label="默认值" min-width="130" /><el-table-column prop="comment" label="注释" min-width="160" /><el-table-column label="操作" width="210"><template #default="scope"><el-button link :disabled="!canEdit()" @click="edit('modify_column', scope.row)">修改类型</el-button><el-button link :disabled="!canEdit()" @click="edit('rename_column', scope.row)">重命名</el-button><el-button link type="danger" :disabled="!canEdit()" @click="remove('drop_column', scope.row.name)">删除</el-button></template></el-table-column></el-table></el-tab-pane><el-tab-pane label="索引" name="indexes"><el-table :data="indexes" height="100%" border><el-table-column prop="name" label="索引" min-width="160" /><el-table-column label="字段" min-width="200"><template #default="scope">{{ scope.row.columns.join(', ') }}</template></el-table-column><el-table-column label="唯一" width="80"><template #default="scope">{{ scope.row.unique ? '是' : '否' }}</template></el-table-column><el-table-column label="操作" width="90"><template #default="scope"><el-button link type="danger" :disabled="!canEdit() || scope.row.name === 'PRIMARY'" @click="remove('drop_index', scope.row.name)">删除</el-button></template></el-table-column></el-table></el-tab-pane><el-tab-pane label="DDL" name="ddl"><pre class="ddl-definition">{{ ddl }}</pre></el-tab-pane></el-tabs>
    <el-dialog :model-value="Boolean(action)" title="修改表结构" width="min(560px,94vw)" align-center :close-on-click-modal="false" @close="action = ''"><el-form label-position="top"><el-form-item label="名称" required><el-input v-model="form.name" :disabled="action === 'modify_column' || action === 'rename_column'" /></el-form-item><el-form-item v-if="action === 'rename_column'" label="新名称" required><el-input v-model="form.newName" /></el-form-item><el-form-item v-if="action === 'add_column' || action === 'modify_column'" label="字段类型" required><el-input v-model="form.columnType" /><small>修改类型保留原字段的默认值、空值约束、字符集和注释。</small></el-form-item><template v-if="action === 'create_index'"><el-form-item label="字段" required><el-select v-model="form.columns" multiple><el-option v-for="column in columns" :key="column.name" :label="column.name" :value="column.name" /></el-select></el-form-item><el-checkbox v-model="form.unique">唯一索引</el-checkbox></template></el-form><template #footer><el-button @click="action = ''">取消</el-button><el-button type="primary" :loading="saving" :disabled="!form.name.trim()" @click="save">保存</el-button></template></el-dialog>
  </section>
</template>
<style scoped>
.structure-document{height:100%;min-height:0;min-width:0;display:flex;flex-direction:column;overflow:hidden}header{flex:none;display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid var(--el-border-color)}header strong{margin-right:auto;overflow-wrap:anywhere}.structure-tabs{flex:1;min-height:0;display:flex;flex-direction:column;padding:0 12px}.structure-tabs :deep(.el-tabs__content){flex:1;min-height:0}.structure-tabs :deep(.el-tab-pane){height:100%;min-height:0;overflow:hidden}.ddl-definition{height:100%;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;margin:0;padding:12px;background:var(--el-fill-color-light)}small{font-size:12px;color:var(--el-text-color-secondary)}
</style>
