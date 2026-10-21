<script setup lang="ts">
import { computed, ref } from 'vue';
import { ElMessage } from 'element-plus';
const props = defineProps<{ assetId: number; database: string; schema: string; table?: string }>();
const emit = defineEmits<{ close: [] }>();
const file = ref<File | null>(null);
const continueOnError = ref(false);
const asyncInsert = ref(true);
const format = computed(() => file.value?.name.split('.').pop()?.toLowerCase() || 'sql');
function selectFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const selected = input.files?.[0];
  if (!selected) return;
  const supported = props.table ? /\.(sql|xlsx|csv|json|txt)$/i : /\.sql$/i;
  if (!supported.test(selected.name) || !selected.size) { file.value = null; input.value = ''; ElMessage.error(props.table ? '请选择非空的 SQL、Excel、CSV、JSON 或 TXT 文件' : '请选择非空的 .sql 转储文件'); return; }
  file.value = selected;
}
function upload() {
  if (!file.value) return;
  const target = { assetId: props.assetId, database: props.database, schema: props.schema, ...(props.table ? { objectName: props.table, importVersion: 2 } : {}), scope: props.table ? 'table' : 'database', format: format.value, options: { continueOnError: continueOnError.value, asyncInsert: asyncInsert.value } };
  window.dispatchEvent(new CustomEvent('database-transfer:upload', { detail: { file: file.value, target } }));
  emit('close');
}
</script>
<template>
  <el-dialog :model-value="true" :title="table ? '导入当前表' : '导入 SQL'" width="min(600px,94vw)" align-center :close-on-click-modal="false" @close="emit('close')"><el-form label-position="top"><el-form-item :label="table ? '目标表' : '目标数据库'"><el-input :model-value="table ? `${database}.${table}` : database" readonly /></el-form-item><el-form-item label="导入文件"><input aria-label="选择导入文件" type="file" :accept="table ? '.sql,.xlsx,.csv,.json,.txt' : '.sql'" @change="selectFile" /></el-form-item><template v-if="format === 'sql'"><el-checkbox v-model="continueOnError">错误时继续</el-checkbox><el-checkbox v-model="asyncInsert">异步插入</el-checkbox><p>异步插入启用后台批量写入；取消勾选后逐行写入。</p></template><p v-else>Excel 读取首个工作表；CSV/TXT 首行为字段名（TXT 使用制表符）；JSON 接受对象数组或以当前表名为键的数组。上传后核对字段映射、类型和行数。</p><el-alert type="info" :closable="false" :title="table ? '仅导入当前表。非 SQL 文件只能写入已有表的数据，预检确认后由后台执行。' : '上传后先预检，再确认执行。支持 MySQL SQL 转储，不支持任意 SQL 脚本或 DELIMITER 存储程序。'" /></el-form><template #footer><el-button @click="emit('close')">取消</el-button><el-button type="primary" :disabled="!file" @click="upload">上传并预检</el-button></template></el-dialog>
</template>
<style scoped>p{color:var(--el-text-color-secondary);font-size:12px}input{max-width:100%}</style>
