<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap, lineNumbers } from '@codemirror/view';
import { defaultHighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { sql } from '@codemirror/lang-sql';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAppContext } from '@app/context';
import { errorMessage } from '@shared/utils/errors';
import { connectionCan } from '../utils/mysqlConnection';
import { formatSqlText, compressSqlText } from '../utils/sqlText';
import DatabaseAccountDialog from './DatabaseAccountDialog.vue';
import DatabaseTableData from './DatabaseTableData.vue';
import DatabaseTableStructure from './DatabaseTableStructure.vue';
import DatabaseObjectEditor, { type DatabaseObjectEditorContext } from './DatabaseObjectEditor.vue';
const DatabaseDiagram = defineAsyncComponent(() => import('./DatabaseDiagram.vue'));
import { createSavedDatabaseQuery, updateSavedDatabaseQuery, executeDatabaseSql, type DatabaseAsset } from '../api/databaseManagement';
import type { DatabaseWorkspaceTab } from './DatabaseWorkspaceTabs.vue';

const props = defineProps<{ document: DatabaseWorkspaceTab; asset: DatabaseAsset }>();
const emit = defineEmits<{ saved: []; dirty: [value: boolean] }>();
const { canUsePageAction } = useAppContext();
const can = (action: string) => canUsePageAction('databaseManagement', action) && connectionCan(props.asset, action);
const editorHost = ref<HTMLElement | null>(null);
const sqlText = ref('');
const resultRows = ref<Record<string, unknown>[]>([]);
const resultColumns = ref<string[]>([]);
const resultMessage = ref('');
const running = ref(false);
const saving = ref(false);
const savedId = ref<number | null>(null);
const savedText = ref('');
const database = props.document.database || '';
const schema = props.document.schema || '';
const tableTarget = computed(() => ({ assetId: props.asset.id, database, schema, table: props.document.table || '' }));
const editorContext = computed<DatabaseObjectEditorContext>(() => ({ assetId: props.asset.id, database, schema, dbType: props.asset.dbType, mode: 'create', objectType: 'table', name: 'new_table' }));
let view: EditorView | null = null;
let controller: AbortController | null = null;
let disposed = false;

async function run() {
  if (!can('execute_sql') || running.value) return;
  const selected = view?.state.sliceDoc(view.state.selection.main.from, view.state.selection.main.to);
  const statement = (selected || sqlText.value).trim();
  if (!statement) return;
  running.value = true;
  try {
    if (!/^(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b/i.test(statement)) await ElMessageBox.confirm('这条语句可能修改数据库内容，确定执行吗？', `执行 SQL · ${database}`, { type: 'warning', confirmButtonText: '确认执行', cancelButtonText: '取消' });
    if (disposed) return;
    controller = new AbortController();
    const result = await executeDatabaseSql(props.asset.id, statement, database, controller.signal);
    resultRows.value = result.rows; resultColumns.value = result.columns;
    resultMessage.value = `执行完成 · ${result.affected} 行 · ${result.elapsedMs} ms`;
  } catch (error) { if (error !== 'cancel' && error !== 'close' && !disposed) { resultMessage.value = errorMessage(error); ElMessage.error(resultMessage.value); } }
  finally { running.value = false; controller = null; }
}
function transform(format: boolean) {
  if (!view) return;
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: format ? formatSqlText(sqlText.value) : compressSqlText(sqlText.value) } });
}
async function saveQuery() {
  if (saving.value || !sqlText.value.trim() || !can('execute_sql')) return;
  saving.value = true;
  try {
    const text = sqlText.value;
    if (savedId.value) await updateSavedDatabaseQuery(savedId.value, { sql: text });
    else {
      const { value } = await ElMessageBox.prompt('查询名称', '保存查询', { inputValue: `查询_${database}`, inputValidator: value => !!value?.trim() || '请输入查询名称', confirmButtonText: '保存', cancelButtonText: '取消' });
      if (disposed) return;
      savedId.value = (await createSavedDatabaseQuery({ assetId: props.asset.id, database, schema, name: value.trim(), sql: text, pinned: false })).id;
    }
    savedText.value = text; emit('dirty', sqlText.value !== text); emit('saved'); ElMessage.success('查询已保存');
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error)); }
  finally { saving.value = false; }
}
onMounted(() => {
  if (props.document.documentType === 'query' && editorHost.value) {
    view = new EditorView({ parent: editorHost.value, state: EditorState.create({ doc: sqlText.value, extensions: [lineNumbers(), history(), keymap.of([{ key: 'Mod-Enter', run: () => { void run(); return true; } }, { key: 'Mod-s', run: () => { void saveQuery(); return true; } }, ...defaultKeymap, ...historyKeymap]), sql(), syntaxHighlighting(defaultHighlightStyle), EditorView.updateListener.of(update => { if (update.docChanged) { sqlText.value = update.state.doc.toString(); emit('dirty', sqlText.value !== savedText.value); } }), EditorView.theme({ '&': { height: '100%', fontSize: '13px', backgroundColor: 'var(--el-bg-color)', color: 'var(--el-text-color-primary)' }, '.cm-scroller': { overflow: 'auto', fontFamily: 'monospace' }, '.cm-gutters': { backgroundColor: 'var(--el-fill-color-light)', color: 'var(--el-text-color-secondary)' }, '.cm-content': { caretColor: 'var(--el-text-color-primary)' } })] }) });
  }
});
onUnmounted(() => { disposed = true; controller?.abort(); view?.destroy(); });
</script>

<template>
  <section v-if="document.documentType === 'query'" class="document-panel query-panel">
    <header><strong>{{ database }} · SQL 查询</strong><el-button type="primary" :disabled="!can('execute_sql')" :loading="running" @click="run">执行（Ctrl+Enter）</el-button><el-button :disabled="!can('execute_sql')" :loading="saving" @click="saveQuery">保存查询</el-button><el-button @click="transform(true)">格式化</el-button><el-button @click="transform(false)">压缩</el-button></header>
    <div ref="editorHost" class="sql-editor"></div>
    <p v-if="resultMessage" role="status" class="query-status">{{ resultMessage }}</p>
    <el-table v-if="resultColumns.length" :data="resultRows" border height="38%"><el-table-column v-for="field in resultColumns" :key="field" :prop="field" :label="field" min-width="140" /></el-table>
  </section>
  <DatabaseDiagram v-else-if="document.documentType === 'er'" :asset-id="asset.id" :database="database" />
  <DatabaseTableData v-else-if="document.documentType === 'table-data'" :asset="asset" :target="tableTarget" @dirty="emit('dirty', $event)" />
  <DatabaseTableStructure v-else-if="document.documentType === 'table-structure'" :asset="asset" :target="tableTarget" @dirty="emit('dirty', $event)" @saved="emit('saved')" />
  <DatabaseObjectEditor v-else-if="document.documentType === 'table' || document.documentType === 'table-create'" embedded :model-value="true" :readonly="!can('manage_schema')" :context="editorContext" @saved="emit('dirty', false); emit('saved')" />
  <DatabaseAccountDialog v-else-if="can('manage_accounts')" embedded :read-only="!connectionCan(asset, 'write_accounts')" :model-value="true" :asset-id="asset.id" :database="database" :db-type="asset.dbType" :schema="schema" />
  <el-empty v-else description="当前账号没有账号管理权限" />
</template>

<style scoped>
.document-panel{height:100%;display:flex;flex-direction:column;min-width:0;min-height:0}.document-panel>header{flex:none;display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--el-border-color)}.document-panel>header strong{margin-right:auto}.sql-editor{flex:1;min-height:150px;overflow:auto;border-bottom:1px solid var(--el-border-color)}.query-status{padding:8px 14px;margin:0;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:90px;overflow:auto}
</style>
