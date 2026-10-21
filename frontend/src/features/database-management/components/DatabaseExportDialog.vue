<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { errorMessage } from '@shared/utils/errors';
import { listDatabaseObjects, getDatabaseTree } from '../api/databaseManagement';
import { chooseExportDestination, destinationMode } from '../utils/exportDestination';

export type ExportFormat = 'sql' | 'xlsx' | 'dictionary' | 'txt' | 'csv' | 'json';
export interface ExportTarget { assetId: number; database: string; schema: string; dbType: string; format: ExportFormat; table?: string; }
const props = defineProps<{ target: ExportTarget | null; canStructure: boolean }>();
const emit = defineEmits<{ close: [] }>();
const tables = ref<string[]>([]);
const selected = ref<string[]>([]);
const schemas = ref<string[]>([]);
const schema = ref('');
const loading = ref(false);
const busy = ref(false);
const failure = ref('');
const structure = ref(true);
const data = ref(true);
const format = ref<ExportFormat>('sql');
const options = ref({ continueOnError: false, batchInsert: true, upsert: false, dropTable: false });
const names = { sql: 'SQL', xlsx: 'Excel', dictionary: '数据字典', txt: 'TXT', csv: 'CSV', json: 'JSON' };
const descriptions = { sql: '生成一个 SQL 文件，可选择表结构和表数据。', xlsx: '生成一个 Excel 文件，每张表对应一个工作表，首行为字段名。', dictionary: '生成数据字典 Excel，按表汇总主键、字段类型、默认值和注释。', txt: '生成一个 TXT 文件，按表分段，字段之间用制表符分隔。', csv: '每张表生成一个 CSV 文件，首行为字段名。', json: '生成一个 JSON 文件，以表名为键、数据行数组为值。' };
const valid = computed(() => selected.value.length && !loading.value && !failure.value && (format.value !== 'sql' || structure.value || data.value));
let version = 0;
async function loadTables() {
  const target = props.target;
  if (!target) return;
  const request = ++version;
  loading.value = true; failure.value = ''; selected.value = []; tables.value = [];
  try {
    if (target.table) { tables.value = [target.table]; selected.value = [target.table]; return; }
    const result = await listDatabaseObjects(target.assetId, target.database, schema.value, 'table');
    if (request !== version) return;
    tables.value = result.objects.map(item => item.name);
    selected.value = target.table ? tables.value.filter(name => name === target.table) : [...tables.value];
  } catch (error) { if (request === version) failure.value = errorMessage(error); }
  finally { if (request === version) loading.value = false; }
}
watch(() => props.target, async target => {
  const request = ++version;
  if (!target) return;
  schema.value = target.schema; schemas.value = []; structure.value = props.canStructure; data.value = true;
  format.value = target.format;
  options.value = { continueOnError: false, batchInsert: true, upsert: false, dropTable: false };
  failure.value = ''; loading.value = true;
  try {
    if (['postgresql', 'kingbase', 'sqlserver', 'oracle', 'dameng'].includes(target.dbType)) {
      const tree = await getDatabaseTree(target.assetId, target.database);
      if (request !== version) return;
      schemas.value = tree.schemas;
      if (schemas.value.length && !schemas.value.includes(schema.value)) schema.value = schemas.value[0];
    } else schema.value = '';
    await loadTables();
  } catch (error) { if (request === version) { failure.value = errorMessage(error); loading.value = false; } }
}, { immediate: true });

async function start() {
  if (!props.target || !valid.value || busy.value) return;
  busy.value = true;
  const target = { ...props.target, schema: schema.value, format: format.value };
  const extension = target.format === 'dictionary' ? 'xlsx' : target.format;
  const fileName = target.table ? `${target.table}.${extension}` : `${target.database}-${target.format}.zip`;
  const payload = { ...target, objectName: target.table || '', direction: 'export', scope: target.table ? 'table' : 'database', exportVersion: 2, tables: target.table ? [target.table] : [...selected.value], options: { ...options.value }, content: structure.value && data.value ? 'structure_data' : structure.value ? 'structure' : 'data', fileName };
  try {
    const destination = await chooseExportDestination(payload.fileName);
    window.dispatchEvent(new CustomEvent('database-export:start', { detail: { payload, destination } }));
    emit('close');
  } catch (error) { if ((error as DOMException).name !== 'AbortError') ElMessage.error(errorMessage(error)); }
  finally { busy.value = false; }
}
</script>

<template>
  <el-dialog :model-value="Boolean(target)" :title="`数据导出 · ${names[format]}`" width="min(580px, 94vw)" align-center :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @close="emit('close')">
    <el-form v-if="target" v-loading="loading" label-position="top" class="database-export-form">
      <el-form-item v-if="!target.table" label="Schema">
        <el-select v-if="schemas.length" v-model="schema" :disabled="busy" @change="loadTables"><el-option v-for="name in schemas" :key="name" :label="name" :value="name" /></el-select>
        <el-input v-else :model-value="target.database" readonly />
      </el-form-item>
      <el-form-item label="表">
        <el-input v-if="target.table" :model-value="`${target.database}.${target.table}`" readonly />
        <el-select v-else v-model="selected" multiple filterable :disabled="busy || loading" placeholder="请选择导出表" style="width:100%">
          <el-option v-for="name in tables" :key="name" :label="name" :value="name" />
        </el-select>
        <div v-if="!target.table" class="export-selection"><span>已选择 {{ selected.length }} / {{ tables.length }} 张表</span><el-button link :disabled="busy" @click="selected = [...tables]">全选</el-button><el-button link :disabled="busy" @click="selected = []">清空</el-button></div>
      </el-form-item>
      <el-form-item v-if="target.table" label="文件格式"><el-select v-model="format" :disabled="busy"><el-option v-for="(label, value) in names" :key="value" :label="label" :value="value" :disabled="value === 'dictionary' && !canStructure" /></el-select></el-form-item>
      <el-form-item label="选项">
        <div class="export-options">
          <el-checkbox v-model="options.continueOnError" :disabled="busy">发生错误继续执行</el-checkbox>
          <template v-if="format === 'sql'">
            <el-checkbox v-model="options.batchInsert" :disabled="busy || !data">批量语句</el-checkbox>
            <el-checkbox v-model="options.upsert" :disabled="busy || !data">主键存在则更新</el-checkbox>
            <el-checkbox v-model="structure" :disabled="busy || !canStructure">表结构</el-checkbox>
            <el-checkbox v-model="data" :disabled="busy">表数据</el-checkbox>
            <el-checkbox v-model="options.dropTable" :disabled="busy || !structure">Drop Table If Exists</el-checkbox>
          </template>
        </div>
      </el-form-item>
      <p class="export-hint">{{ descriptions[format] }}</p>
      <p class="export-hint">{{ target.table ? '仅导出当前表，保存为所选格式文件。' : '多表导出打包为 ZIP。' }}{{ destinationMode() === 'directory' ? '请选择本地文件夹，同名文件自动编号。' : '文件保存到所选位置或浏览器下载目录。' }}</p>
      <el-alert v-if="failure" :title="failure" type="error" :closable="false" />
      <el-button v-if="failure" link :disabled="loading" @click="loadTables">重新读取表清单</el-button>
    </el-form>
    <template #footer><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="busy" :disabled="!valid" @click="start">开始</el-button></template>
  </el-dialog>
</template>

<style scoped>
.database-export-form{padding:0 4px}.export-options{display:flex;flex-wrap:wrap;gap:0 16px;align-items:flex-start}.export-options :deep(.el-checkbox){margin:0;height:28px;max-width:100%}.export-selection{display:flex;gap:10px;align-items:center;font-size:12px;margin-top:8px}.export-hint{font-size:12px;color:var(--el-text-color-secondary);line-height:1.6}.database-export-form :deep(.el-select){width:100%}
.database-export-form :deep(.el-input__wrapper),.database-export-form :deep(.el-select__wrapper){box-shadow:0 0 0 1px var(--el-border-color) inset!important;background:var(--el-fill-color-blank)}
.database-export-form :deep(.el-input__wrapper.is-focus),.database-export-form :deep(.el-select__wrapper.is-focused){box-shadow:0 0 0 1px var(--el-color-primary) inset!important}
</style>
