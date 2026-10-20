<script setup lang="ts">
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
const props = defineProps<{ assetId: number; database: string; schema: string }>();
const emit = defineEmits<{ close: [] }>();
const file = ref<File | null>(null);
const continueOnError = ref(false);
const asyncInsert = ref(true);
function selectFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const selected = input.files?.[0];
  if (!selected) return;
  if (!/\.sql$/i.test(selected.name) || !selected.size) { file.value = null; input.value = ''; ElMessage.error('请选择非空的 .sql 转储文件'); return; }
  file.value = selected;
}
function upload() {
  if (!file.value) return;
  window.dispatchEvent(new CustomEvent('database-transfer:upload', { detail: { file: file.value, target: { assetId: props.assetId, database: props.database, schema: props.schema, scope: 'database', format: 'sql', options: { continueOnError: continueOnError.value, asyncInsert: asyncInsert.value } } } }));
  emit('close');
}
</script>
<template>
  <el-dialog :model-value="true" title="导入 SQL" width="min(600px,94vw)" :close-on-click-modal="false" @close="emit('close')"><el-form label-position="top"><el-form-item label="目标数据库"><el-input :model-value="database" readonly /></el-form-item><el-form-item label="SQL 文件"><input aria-label="选择 SQL 文件" type="file" accept=".sql" @change="selectFile" /></el-form-item><el-checkbox v-model="continueOnError">错误时继续</el-checkbox><el-checkbox v-model="asyncInsert">异步插入</el-checkbox><p>异步插入启用后台批量写入；取消勾选后逐行写入。所有导入均在后台任务中执行。</p><el-alert type="info" :closable="false" title="上传后先预检，再确认执行。支持 MySQL SQL 转储，不支持任意 SQL 脚本或 DELIMITER 存储程序。" /></el-form><template #footer><el-button @click="emit('close')">取消</el-button><el-button type="primary" :disabled="!file" @click="upload">上传并预检</el-button></template></el-dialog>
</template>
<style scoped>p{color:var(--el-text-color-secondary);font-size:12px}input{max-width:100%}</style>
