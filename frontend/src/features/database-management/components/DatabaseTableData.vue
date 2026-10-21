<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, toRaw, watch } from 'vue';
import { ArrowDownUp, Columns3, Download, Filter, GitBranch, Minus, Plus, RefreshCw, Save, Undo2, Upload } from '@lucide/vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAppContext } from '@app/context';
import { errorMessage } from '@shared/utils/errors';
import { connectionCan } from '../utils/mysqlConnection';
import { commitDatabaseRows, getDatabaseColumns, getDatabaseTableData, modifyDatabaseRow, type DatabaseAsset, type DatabaseColumn, type TableReference } from '../api/databaseManagement';
import DatabaseExportDialog, { type ExportTarget } from './DatabaseExportDialog.vue';
import DatabaseImportDialog from './DatabaseImportDialog.vue';

const props = defineProps<{ asset: DatabaseAsset; target: TableReference }>();
const emit = defineEmits<{ dirty: [value: boolean] }>();
const { canUsePageAction } = useAppContext();
const can = (action: string) => canUsePageAction('databaseManagement', action === 'import_data' ? 'import_export' : action) && connectionCan(props.asset, action);
const columns = ref<DatabaseColumn[]>([]);
const rows = ref<Record<string, unknown>[]>([]);
const selectedRow = ref<Record<string, unknown> | null>(null);
const loading = ref(false);
const saving = ref(false);
const failure = ref('');
const page = ref(1);
const pageSize = ref(50);
const total = ref(0);
const transaction = ref(false);
type Change = { action: 'insert' | 'update' | 'delete'; values: Record<string, unknown>; key: Record<string, unknown> };
const changes = ref<Change[]>([]);
const insertedRows = new WeakMap<Record<string, unknown>, Change>();
const pendingInsert = ref<Change | null>(null);
const selectedInsert = computed(() => selectedRow.value ? insertedRows.get(toRaw(selectedRow.value)) : undefined);
const visibleFields = ref<string[]>([]);
const whereField = ref('');
const whereValue = ref('');
const sort = ref('');
const direction = ref('asc');
const editing = ref<'insert' | 'update' | null>(null);
const draft = ref<Record<string, string>>({});
const included = ref<string[]>([]);
const original = ref<Record<string, unknown>>({});
const exportTarget = ref<ExportTarget | null>(null);
const importing = ref(false);
const primary = computed(() => columns.value.filter(column => column.column_key === 'PRI').map(column => column.name));
const dirty = computed(() => changes.value.length > 0 || Boolean(editing.value));
watch(dirty, value => emit('dirty', value));
const keyOf = (row: Record<string, unknown>) => Object.fromEntries(primary.value.map(name => [name, row[name]]));
const sameKey = (row: Record<string, unknown>, key: Record<string, unknown>) => Object.keys(key).length > 0 && Object.entries(key).every(([name, value]) => row[name] === value);
const displayedRows = computed(() => {
  let result = rows.value.map(row => ({ ...row }));
  for (const change of changes.value) {
    if (change.action === 'insert') { const inserted = { ...change.values }; insertedRows.set(inserted, change); result.push(inserted); }
    else if (change.action === 'delete') result = result.filter(row => !sameKey(row, change.key));
    else result = result.map(row => sameKey(row, change.key) ? { ...row, ...change.values } : row);
  }
  return result;
});
let loadVersion = 0;
async function load() {
  if (!can('view_data')) return;
  const request = ++loadVersion;
  loading.value = true; failure.value = ''; selectedRow.value = null;
  try {
    const result = await getDatabaseTableData(props.target.assetId, { ...props.target, page: page.value, pageSize: pageSize.value, sort: sort.value, direction: direction.value, whereField: whereField.value, whereValue: whereValue.value });
    if (request === loadVersion) { rows.value = result.rows; total.value = result.total; }
  } catch (error) { if (request === loadVersion) failure.value = errorMessage(error); }
  finally { if (request === loadVersion) loading.value = false; }
}
function openRow(action: 'insert' | 'update', row?: Record<string, unknown>) {
  const inserted = row ? insertedRows.get(toRaw(row)) : undefined;
  if (!can('modify_data') || saving.value || (action === 'update' && !primary.value.length && !inserted)) return;
  pendingInsert.value = inserted || null;
  original.value = { ...row }; editing.value = action;
  included.value = action === 'update' ? Object.keys(row || {}) : [];
  draft.value = Object.fromEntries(columns.value.map(column => [column.name, row?.[column.name] === undefined ? 'null' : JSON.stringify(row[column.name])]));
}
async function saveRow() {
  if (!editing.value || saving.value || !can('modify_data')) return;
  try {
    const values = Object.fromEntries(included.value.map(name => [name, JSON.parse(draft.value[name])]));
    if (!Object.keys(values).length) throw new Error('请至少选择一个字段');
    const change: Change = { action: editing.value, values, key: editing.value === 'update' ? keyOf(original.value) : {} };
    if (transaction.value) {
      if (pendingInsert.value) pendingInsert.value.values = values;
      else { if (changes.value.length >= 500) throw new Error('每次事务最多暂存 500 项修改，请先保存'); changes.value.push(change); }
    } else {
      saving.value = true;
      await modifyDatabaseRow(props.target.assetId, { ...props.target, ...change });
      await load();
    }
    editing.value = null;
  } catch (error) { ElMessage.error(error instanceof SyntaxError ? '字段值请使用 JSON 格式，例如 "文本"、123 或 null' : errorMessage(error)); }
  finally { saving.value = false; }
}
async function remove() {
  if (!selectedRow.value || saving.value || !can('modify_data') || !primary.value.length && !selectedInsert.value) return;
  const inserted = selectedInsert.value;
  const row = { ...selectedRow.value };
  try {
    await ElMessageBox.confirm('确认删除选中行？', '删除数据', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' });
    const change: Change = { action: 'delete', key: keyOf(row), values: {} };
    if (inserted) changes.value = changes.value.filter(change => change !== inserted);
    else if (transaction.value) {
      if (changes.value.length >= 500) throw new Error('每次事务最多暂存 500 项修改，请先保存');
      changes.value.push(change);
    } else { await modifyDatabaseRow(props.target.assetId, { ...props.target, ...change }); await load(); }
    selectedRow.value = null;
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error)); }
}
async function save() {
  if (editing.value) { await saveRow(); return; }
  if (!changes.value.length || saving.value || !can('modify_data')) return;
  saving.value = true;
  try {
    await commitDatabaseRows(props.target.assetId, { changes: changes.value.map(change => ({ ...props.target, ...change })) });
    changes.value = []; await load(); ElMessage.success('事务已提交');
  } catch (error) { ElMessage.error(errorMessage(error)); }
  finally { saving.value = false; }
}
async function undo() {
  if (!dirty.value || saving.value) return;
  try {
    await ElMessageBox.confirm('撤销当前标签页所有未提交修改？', '返回', { confirmButtonText: '撤销修改', cancelButtonText: '取消' });
    changes.value = []; editing.value = null; selectedRow.value = null;
  } catch { return; }
}
function toggleTransaction() {
  if (changes.value.length) { ElMessage.warning('请先保存或返回撤销暂存修改'); return; }
  transaction.value = !transaction.value;
}
function filter() { page.value = 1; void load(); }
function toggleField(name: string, checked: unknown) { included.value = checked ? [...included.value, name] : included.value.filter(field => field !== name); }
function openExport() { exportTarget.value = { ...props.target, dbType: props.asset.dbType, format: 'sql' }; }
onMounted(async () => {
  try { columns.value = (await getDatabaseColumns(props.target.assetId, props.target.database, props.target.table, props.target.schema)).columns; visibleFields.value = columns.value.map(column => column.name); await load(); }
  catch (error) { failure.value = errorMessage(error); }
});
onUnmounted(() => { loadVersion++; });
</script>

<template>
  <section class="table-data-document" :aria-label="`${target.table} 表数据`">
    <header class="table-toolbar" role="toolbar" aria-label="表数据操作">
      <strong>{{ target.table }}</strong>
      <el-button title="事务" aria-label="事务" :type="transaction ? 'primary' : 'default'" :aria-pressed="transaction" :disabled="!can('modify_data') || saving" @click="toggleTransaction"><GitBranch :size="16" /></el-button>
      <el-button title="刷新" aria-label="刷新" :disabled="loading || saving" @click="load"><RefreshCw :size="16" /></el-button>
      <el-button title="增加" aria-label="增加" :disabled="!can('modify_data') || saving" @click="openRow('insert')"><Plus :size="16" /></el-button>
      <el-button title="减少" aria-label="减少" :disabled="!can('modify_data') || !selectedRow || !primary.length && !selectedInsert || saving" @click="remove"><Minus :size="16" /></el-button>
      <el-button title="保存" aria-label="保存" :loading="saving" :disabled="!can('modify_data') || !dirty" @click="save"><Save :size="16" /></el-button>
      <el-button title="返回" aria-label="返回" :disabled="!dirty || saving" @click="undo"><Undo2 :size="16" /></el-button>
      <el-popover trigger="click" :width="260"><template #reference><el-button title="字段" aria-label="字段"><Columns3 :size="16" /></el-button></template><div class="field-picker"><el-checkbox-group v-model="visibleFields"><el-checkbox v-for="column in columns" :key="column.name" :value="column.name">{{ column.name }}</el-checkbox></el-checkbox-group></div></el-popover>
      <el-popover trigger="click" :width="280"><template #reference><el-button title="筛选" aria-label="筛选"><Filter :size="16" /></el-button></template><el-form label-position="top"><el-form-item label="字段"><el-select v-model="whereField" clearable><el-option v-for="column in columns" :key="column.name" :value="column.name" :label="column.name" /></el-select></el-form-item><el-form-item label="等于"><el-input v-model="whereValue" @keyup.enter="filter" /></el-form-item><el-button @click="filter">应用筛选</el-button></el-form></el-popover>
      <el-popover trigger="click" :width="280"><template #reference><el-button title="排序" aria-label="排序"><ArrowDownUp :size="16" /></el-button></template><el-form label-position="top"><el-form-item label="字段"><el-select v-model="sort" clearable><el-option v-for="column in columns" :key="column.name" :value="column.name" :label="column.name" /></el-select></el-form-item><el-radio-group v-model="direction"><el-radio value="asc">升序</el-radio><el-radio value="desc">降序</el-radio></el-radio-group><el-button @click="filter">应用排序</el-button></el-form></el-popover>
      <el-button title="导入" aria-label="导入" :disabled="!can('import_data')" @click="importing = true"><Upload :size="16" /></el-button>
      <el-button title="导出" aria-label="导出" :disabled="!can('import_export')" @click="openExport"><Download :size="16" /></el-button>
      <span v-if="transaction" class="transaction-state">事务暂存 {{ changes.length }} 项</span>
    </header>
    <el-alert v-if="failure" :title="failure" type="error" :closable="false" />
    <p v-if="!primary.length" class="table-hint">该表没有主键，无法安全编辑或删除单行。双击数据行编辑。</p>
    <div class="data-grid"><el-table v-loading="loading" :data="displayedRows" border stripe height="100%" highlight-current-row @current-change="selectedRow = $event" @row-dblclick="row => openRow('update', row)"><el-table-column v-for="field in visibleFields" :key="field" :prop="field" :label="field" min-width="150" show-overflow-tooltip /></el-table></div>
    <footer><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[25,50,100,200]" :total="total" layout="total, prev, pager, next, sizes" :disabled="loading" @current-change="load" @size-change="filter" /></footer>
    <el-dialog :model-value="Boolean(editing)" :title="editing === 'insert' ? '增加数据' : '编辑数据'" width="min(640px,94vw)" align-center :close-on-click-modal="false" :show-close="!saving" @close="editing = null"><p class="table-hint">勾选写入字段，值使用 JSON 格式："文本"、123、true、null。未勾选字段保留默认值。</p><el-form label-position="top" class="row-form"><el-form-item v-for="column in columns" :key="column.name"><template #label><el-checkbox :model-value="included.includes(column.name)" @change="value => toggleField(column.name, value)">{{ column.name }} · {{ column.type }}</el-checkbox></template><el-input v-model="draft[column.name]" :disabled="!included.includes(column.name) || saving" /></el-form-item></el-form><template #footer><el-button :disabled="saving" @click="editing = null">取消</el-button><el-button type="primary" :loading="saving" @click="saveRow">{{ transaction ? '暂存' : '保存' }}</el-button></template></el-dialog>
    <DatabaseImportDialog v-if="importing" v-bind="target" @close="importing = false" />
    <DatabaseExportDialog v-if="exportTarget" :target="exportTarget" :can-structure="can('manage_schema')" @close="exportTarget = null" />
  </section>
</template>

<style scoped>
.table-data-document{height:100%;min-height:0;min-width:0;display:flex;flex-direction:column;overflow:hidden}.table-toolbar{display:flex;align-items:center;gap:4px;flex-wrap:wrap;flex:none;padding:8px 12px;border-bottom:1px solid var(--el-border-color);background:var(--el-fill-color-light)}.table-toolbar strong{font-size:13px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-right:8px}.table-toolbar :deep(.el-button){margin:0;width:32px;padding:7px}.transaction-state,.table-hint{font-size:12px;color:var(--el-text-color-secondary)}.table-hint{padding:6px 12px;margin:0}.data-grid{flex:1;min-height:0;min-width:0;overflow:hidden}footer{flex:none;padding:8px;overflow-x:auto}.field-picker{max-height:280px;overflow:auto}.field-picker :deep(.el-checkbox){display:flex;margin:0}.row-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px;max-height:55vh;overflow:auto}.row-form :deep(.el-form-item){min-width:0}.row-form :deep(.el-checkbox__label){white-space:normal;overflow-wrap:anywhere}@media(max-width:600px){.row-form{grid-template-columns:minmax(0,1fr)}.table-toolbar{padding:6px}.table-toolbar strong{max-width:110px}.transaction-state{flex-basis:100%}}
</style>
