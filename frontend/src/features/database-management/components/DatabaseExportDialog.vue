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
const options = ref({ continueOnError: false, batchInsert: true, upsert: false, dropTable: false });
const names = { sql: 'SQL', xlsx: 'Excel', dictionary: '数据字典', txt: 'TXT', csv: 'CSV', json: 'JSON' };
const descriptions = { sql: '生成一个 SQL 文件，可选择表结构和表数据。', xlsx: '生成一个 Excel 文件，每张表对应一个工作表，首行为字段名。', dictionary: '生成数据字典 Excel，按表汇总主键、字段类型、默认值和注释。', txt: '生成一个 TXT 文件，按表分段，字段之间用制表符分隔。', csv: '每张表生成一个 CSV 文件，首行为字段名。', json: '生成一个 JSON 文件，以表名为键、数据行数组为值。' };
const valid = computed(() => selected.value.length && !loading.value && !failure.value && (props.target?.format !== 'sql' || structure.value || data.value));
let version = 0;
async function loadTables() {
  const target = props.target;
  if (!target) return;
  const request = ++version;
  loading.value = true; failure.value = ''; selected.value = []; tables.value = [];
  try {
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
  const target = { ...props.target, schema: schema.value };
  const payload = { ...target, direction: 'export', scope: target.table ? 'table' : 'database', exportVersion: 2, tables: [...selected.value], options: { ...options.value }, content: structure.value && data.value ? 'structure_data' : structure.value ? 'structure' : 'data', fileName: `${target.database}-${target.format}.zip` };
  try {
    const destination = await chooseExportDestination(payload.fileName);
    window.dispatchEvent(new CustomEvent('database-export:start', { detail: { payload, destination } }));
    emit('close');
  } catch (error) { if ((error as DOMException).name !== 'AbortError') ElMessage.error(errorMessage(error)); }
  finally { busy.value = false; }
}
</script>

<template>
  <el-dialog :model-value="Boolean(target)" :title="`数据导出 · ${target ? names[target.format] : ''}`" width="min(580px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @close="emit('close')">
    <el-form v-if="target" v-loading="loading" label-position="top" class="database-export-form">
      <el-form-item label="Schema">
        <el-select v-if="schemas.length" v-model="schema" :disabled="busy" @change="loadTables"><el-option v-for="name in schemas" :key="name" :label="name" :value="name" /></el-select>
        <el-input v-else :model-value="target.database" readonly />
      </el-form-item>
      <el-form-item label="表">
        <el-select v-model="selected" multiple filterable :disabled="busy || loading" placeholder="请选择导出表" style="width:100%">
          <el-option v-for="name in tables" :key="name" :label="name" :value="name" />
        </el-select>
        <div class="export-selection"><span>已选择 {{ selected.length }} / {{ tables.length }} 张表</span><el-button link :disabled="busy" @click="selected = [...tables]">全选</el-button><el-button link :disabled="busy" @click="selected = []">清空</el-button></div>
      </el-form-item>
      <el-form-item label="选项">
        <div class="export-options">
          <el-checkbox v-model="options.continueOnError" :disabled="busy">发生错误继续执行</el-checkbox>
          <template v-if="target.format === 'sql'">
            <el-checkbox v-model="options.batchInsert" :disabled="busy || !data">批量语句</el-checkbox>
            <el-checkbox v-model="options.upsert" :disabled="busy || !data">主键存在则更新</el-checkbox>
            <el-checkbox v-model="structure" :disabled="busy || !canStructure">表结构</el-checkbox>
            <el-checkbox v-model="data" :disabled="busy">表数据</el-checkbox>
            <el-checkbox v-model="options.dropTable" :disabled="busy || !structure">Drop Table If Exists</el-checkbox>
          </template>
        </div>
      </el-form-item>
      <p class="export-hint">{{ descriptions[target.format] }}</p>
      <p class="export-hint">{{ destinationMode() === 'directory' ? '点击开始后选择本地文件夹。同名文件会自动编号，避免覆盖。' : destinationMode() === 'zip' ? '点击开始后选择 ZIP 文件保存位置。' : '此浏览器不支持预选保存位置，将下载 ZIP 到浏览器设置的下载目录。可使用 HTTPS 下的 Chrome/Edge 预选本地目录。' }}</p>
      <el-alert v-if="failure" :title="failure" type="error" :closable="false" />
      <el-button v-if="failure" link :disabled="loading" @click="loadTables">重新读取表清单</el-button>
    </el-form>
    <template #footer><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="busy" :disabled="!valid" @click="start">开始</el-button></template>
  </el-dialog>
</template>

<style scoped>
.database-export-form{padding:8px 4px}.export-options{display:flex;flex-direction:column;align-items:flex-start}.export-options :deep(.el-checkbox){margin:0;height:28px}.export-selection{display:flex;gap:10px;align-items:center;font-size:12px;margin-top:8px}.export-hint{font-size:12px;color:var(--el-text-color-secondary);line-height:1.6}.database-export-form :deep(.el-select){width:100%}
.database-export-form :deep(.el-input__wrapper),.database-export-form :deep(.el-select__wrapper){box-shadow:0 0 0 1px var(--el-border-color) inset!important;background:var(--el-fill-color-blank)}
.database-export-form :deep(.el-input__wrapper.is-focus),.database-export-form :deep(.el-select__wrapper.is-focused){box-shadow:0 0 0 1px var(--el-color-primary) inset!important}
</style>
