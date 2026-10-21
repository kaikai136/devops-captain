<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { errorMessage } from '@shared/utils/errors';
import { connectionCan } from '../utils/mysqlConnection';
import { executeTableOperation, getDatabaseTree, listDatabaseObjects, previewTableOperation, type DatabaseAsset, type TableOperationMode, type TableOperationPreview, type TableReference } from '../api/databaseManagement';
const props = defineProps<{ source: TableReference; assets: DatabaseAsset[]; mode: TableOperationMode; initialTarget?: TableReference }>();
const emit = defineEmits<{ close: []; saved: [] }>();
const target = ref<TableReference>({ assetId: 0, database: '', schema: '', table: '', ...props.initialTarget });
const databases = ref<string[]>([]);
const tables = ref<string[]>([]);
const preview = ref<TableOperationPreview | null>(null);
const busy = ref(false);
const loading = ref(false);
const failure = ref('');
const confirmed = ref(false);
const deleteExtras = ref(false);
const policy = ref(props.mode === 'data' ? 'update' : 'append');
const tab = ref('fields');
const title = computed(() => ({ copy: '数据粘贴', structure: '结构同步', data: '数据同步' }[props.mode]));
const targets = computed(() => props.assets.filter(asset => ['mysql', 'mariadb'].includes(asset.dbType) && connectionCan(asset, props.mode === 'structure' ? 'manage_schema' : 'modify_data')));
const displayedSql = computed(() => props.mode === 'structure' && deleteExtras.value ? preview.value?.sqlDeleteExtras || [] : preview.value?.sql || []);
let version = 0;
watch(target, () => { preview.value = null; confirmed.value = false; policy.value = props.mode === 'data' ? 'update' : 'append'; }, { deep: true, flush: 'sync' });
watch([policy, deleteExtras], () => { confirmed.value = false; });
async function loadTables() {
  const request = ++version;
  preview.value = null; loading.value = true; failure.value = ''; tables.value = [];
  if (!target.value.assetId || !target.value.database) { loading.value = false; return; }
  try { const result = await listDatabaseObjects(target.value.assetId, target.value.database, target.value.schema, 'table'); if (request === version) tables.value = result.objects.map(table => table.name); }
  catch (error) { if (request === version) failure.value = errorMessage(error); }
  finally { if (request === version) loading.value = false; }
}
async function loadDatabases() {
  const request = ++version;
  loading.value = true; failure.value = ''; databases.value = []; tables.value = [];
  try { const result = await getDatabaseTree(target.value.assetId); if (request === version) databases.value = result.databases; }
  catch (error) { if (request === version) failure.value = errorMessage(error); }
  finally { if (request === version) loading.value = false; }
}
async function changeAsset() { target.value.database = ''; target.value.schema = ''; target.value.table = ''; await loadDatabases(); }
async function changeDatabase() { target.value.schema = ''; target.value.table = ''; await loadTables(); }
async function inspect() {
  if (busy.value || loading.value || !target.value.table) return;
  busy.value = true; failure.value = ''; confirmed.value = false;
  try { preview.value = await previewTableOperation(props.source, { ...target.value }, props.mode); }
  catch (error) { failure.value = errorMessage(error); }
  finally { busy.value = false; }
}
async function execute() {
  if (!preview.value?.canExecute || !confirmed.value || busy.value) return;
  busy.value = true; failure.value = '';
  try {
    const task = await executeTableOperation(preview.value.previewId, { confirmed: true, conflictPolicy: policy.value, deleteTargetExtras: deleteExtras.value });
    window.dispatchEvent(new CustomEvent('database-import:show', { detail: task }));
    window.dispatchEvent(new CustomEvent('database-transfer:open'));
    ElMessage.success('表操作已提交后台任务'); emit('saved'); emit('close');
  } catch (error) { failure.value = errorMessage(error); }
  finally { busy.value = false; }
}
onMounted(async () => { if (target.value.assetId) { await loadDatabases(); if (target.value.database) await loadTables(); } });
</script>
<template>
  <el-dialog :model-value="true" :title="title" width="min(900px,94vw)" align-center :close-on-click-modal="false" :show-close="!busy" @close="emit('close')">
    <div class="operation-body"><p class="source-reference">来源：{{ assets.find(asset => asset.id === source.assetId)?.name }} / {{ source.database }} / {{ source.table }}</p>
      <el-form label-position="top" class="target-form"><el-form-item label="目标连接" required><el-select v-model="target.assetId" :disabled="busy" filterable @change="changeAsset"><el-option v-for="asset in targets" :key="asset.id" :label="asset.name" :value="asset.id" /></el-select></el-form-item><el-form-item label="目标数据库" required><el-select v-model="target.database" :disabled="busy || loading" filterable @change="changeDatabase"><el-option v-for="name in databases" :key="name" :label="name" :value="name" /></el-select></el-form-item><el-form-item label="Schema"><el-input :model-value="target.database" readonly /></el-form-item><el-form-item label="目标表" required><el-select v-model="target.table" :disabled="busy || loading" filterable><el-option v-for="name in tables" :key="name" :label="name" :value="name" /></el-select></el-form-item></el-form>
      <el-alert v-if="failure" :title="failure" type="error" :closable="false" />
      <section v-if="preview?.dataDifference && mode !== 'structure'" class="data-difference">
        <strong>数据差异{{ preview.dataDifference.exact ? '（完整）' : '（抽样预览）' }}</strong>
        <span>已检查 {{ preview.dataDifference.sampledRows.toLocaleString() }} 行</span>
        <span>新增 {{ preview.dataDifference.insertRows.toLocaleString() }}</span>
        <span>更新 {{ preview.dataDifference.updateRows.toLocaleString() }}</span>
        <span>不变 {{ preview.dataDifference.unchangedRows.toLocaleString() }}</span>
        <span>主键冲突 {{ preview.dataDifference.keyConflicts.toLocaleString() }}</span>
      </section>
      <section v-if="preview && mode === 'structure'" class="structure-sql-preview">
        <strong>结构变更 SQL 预览</strong>
        <pre>{{ displayedSql.join(';\n') || '所选同步选项不会产生结构变更' }}</pre>
      </section>
<template v-if="preview"><p>来源 {{ preview.sourceRows.toLocaleString() }} 行 · 目标 {{ preview.targetRows.toLocaleString() }} 行 · 主键 {{ preview.primaryKey.join(', ') || '无' }}</p><el-tabs v-model="tab"><el-tab-pane label="字段差异" name="fields"><el-table :data="preview.fields" border max-height="210"><el-table-column prop="name" label="字段" min-width="130" /><el-table-column prop="change" label="变更" width="110" /><el-table-column prop="source" label="来源" min-width="200" /><el-table-column prop="target" label="目标" min-width="200" /></el-table></el-tab-pane><el-tab-pane label="索引差异" name="indexes"><el-table :data="preview.indexes" border max-height="210"><el-table-column prop="name" label="索引" /><el-table-column prop="change" label="变更" /><el-table-column prop="source" label="来源" min-width="220" /><el-table-column prop="target" label="目标" min-width="220" /></el-table></el-tab-pane><el-tab-pane label="执行 SQL" name="sql"><pre>{{ displayedSql.join(';\n') }}</pre></el-tab-pane></el-tabs><p v-for="warning in preview.warnings" :key="warning" class="warning">{{ warning }}</p><p v-for="conflict in preview.conflicts" :key="conflict" class="error">{{ conflict }}</p><el-checkbox v-if="mode === 'structure'" v-model="deleteExtras">同时删除目标独有字段和索引（默认保留）</el-checkbox><el-form-item v-else label="键冲突处理"><el-select v-model="policy"><el-option label="追加，冲突时失败并回滚" value="append" /><el-option label="跳过冲突行" value="skip" /><el-option v-if="preview.matchingPrimaryKey" label="按主键更新已有行，并新增缺失行" value="update" /></el-select></el-form-item><el-checkbox v-model="confirmed" :disabled="!preview.canExecute">已核对来源、目标和影响范围，确认执行</el-checkbox></template>
    </div><template #footer><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button :loading="busy" :disabled="!target.table || loading" @click="inspect">预览差异</el-button><el-button type="primary" :loading="busy" :disabled="!preview?.canExecute || !confirmed" @click="execute">确认执行</el-button></template>
  </el-dialog>
</template>
<style scoped>
.operation-body{max-height:calc(100dvh - 220px);overflow:auto;min-width:0}.target-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}.target-form :deep(.el-select){width:100%}.source-reference{margin-top:0;overflow-wrap:anywhere}p{font-size:12px;overflow-wrap:anywhere}.warning{color:var(--el-color-warning)}.error{color:var(--el-color-danger)}pre{max-height:210px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}.operation-body :deep(.el-checkbox){max-width:100%;height:auto;min-height:30px}.operation-body :deep(.el-checkbox__label){white-space:normal;overflow-wrap:anywhere}@media(max-width:600px){.target-form{grid-template-columns:minmax(0,1fr)}}
.data-difference{display:flex;gap:8px 16px;flex-wrap:wrap;align-items:center;padding:10px;margin:10px 0;border:1px solid var(--el-border-color);border-radius:4px;font-size:12px}.structure-sql-preview{margin:10px 0}.structure-sql-preview strong{font-size:12px}
</style>
