<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { errorMessage } from '@shared/utils/errors';
import { editMysqlDatabase, getMysqlMetadata, type MysqlDatabaseMetadata } from '../api/databaseManagement';
const props = defineProps<{ assetId: number; database: string }>();
const emit = defineEmits<{ close: []; saved: [] }>();
const metadata = ref<MysqlDatabaseMetadata | null>(null);
const charset = ref('');
const collation = ref('');
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const charsets = computed(() => [...new Set(metadata.value?.choices.map(item => item.charset) || [])]);
const collations = computed(() => metadata.value?.choices.filter(item => item.charset === charset.value) || []);
const preview = computed(() => `ALTER DATABASE \`${props.database.replace(/`/g, '``')}\` CHARACTER SET ${charset.value} COLLATE ${collation.value};`);
function changeCharset() { collation.value = collations.value.find(item => item.collation === metadata.value?.collation)?.collation || collations.value[0]?.collation || ''; }
onMounted(async () => { try { metadata.value = await getMysqlMetadata(props.assetId, props.database); charset.value = metadata.value.charset; collation.value = metadata.value.collation; } catch (err) { error.value = errorMessage(err); } finally { loading.value = false; } });
async function save() {
  if (loading.value || saving.value || !collations.value.some(item => item.collation === collation.value)) return;
  saving.value = true;
  try { await editMysqlDatabase(props.assetId, props.database, charset.value, collation.value); ElMessage.success('数据库设置已保存'); emit('saved'); emit('close'); }
  catch (err) { error.value = errorMessage(err); }
  finally { saving.value = false; }
}
</script>
<template>
  <el-dialog :model-value="true" title="编辑数据库" width="min(620px,94vw)" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving" @close="emit('close')"><el-alert v-if="error" :title="error" type="error" :closable="false" /><el-form v-loading="loading" label-position="top" :disabled="saving"><el-form-item label="数据库名"><el-input :model-value="database" readonly /></el-form-item><el-form-item label="字符编码"><el-select v-model="charset" filterable style="width:100%" @change="changeCharset"><el-option v-for="value in charsets" :key="value" :value="value" /></el-select></el-form-item><el-form-item label="字符集排序规则"><el-select v-model="collation" filterable style="width:100%"><el-option v-for="value in collations" :key="value.collation" :value="value.collation" /></el-select></el-form-item><el-form-item label="SQL 预览"><pre class="database-alter-preview">{{ preview }}</pre></el-form-item><p>修改数据库默认字符集，不转换已有表和字段的数据。</p></el-form><template #footer><el-button :disabled="saving" @click="emit('close')">取消</el-button><el-button type="primary" :loading="saving" :disabled="loading || !collation" @click="save">保存</el-button></template></el-dialog>
</template>
<style scoped>
.database-alter-preview{width:100%;margin:0;padding:14px;box-sizing:border-box;background:var(--el-fill-color-light);color:var(--el-color-primary);white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}p{font-size:12px;color:var(--el-text-color-secondary)}
:deep(.el-input__wrapper),:deep(.el-select__wrapper){box-shadow:0 0 0 1px var(--el-border-color) inset!important;background:var(--el-fill-color-blank)!important}:deep(.el-input__wrapper.is-focus),:deep(.el-select__wrapper.is-focused){box-shadow:0 0 0 1px var(--el-color-primary) inset!important}
</style>
