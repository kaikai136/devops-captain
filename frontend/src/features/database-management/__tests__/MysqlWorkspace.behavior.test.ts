import { readFileSync } from 'node:fs';
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc';
import * as ts from 'typescript';
import * as Vue from 'vue';
import * as diagramUtils from '../utils/databaseDiagram';
import * as connectionUtils from '../utils/mysqlConnection';
import { afterEach, describe, expect, it, vi } from 'vitest';

// Run the actual setup functions with mocked network/UI boundaries; no live database mutations.
const scopes: Vue.EffectScope[] = [];
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); });
function setup(name: string, props: Record<string, unknown> = {}, allowed = true) {
  const { descriptor } = parse(readFileSync(new URL(`../components/${name}.vue`, import.meta.url), 'utf8'));
  const script = compileScript(descriptor, { id: name });
  const rendered = compileTemplate({ source: descriptor.template!.content, filename: name, id: name, compilerOptions: { bindingMetadata: script.bindings } });
  expect(rendered.errors).toEqual([]);
  const mounted: (() => unknown)[] = [];
  const api = new Proxy<Record<string, ReturnType<typeof vi.fn>>>({}, { get(target, key: string) { return target[key] ||= vi.fn().mockResolvedValue({ databases: ['tele', 'other'], objects: [], rows: [], columns: [], affected: 0, elapsedMs: 1 }); } });
  const emit = vi.fn();
  const confirm = vi.fn().mockResolvedValue('confirm');
  const requestConfirm = vi.fn();
  const event = vi.fn();
  const context = { canUsePageAction: () => allowed, showToast: vi.fn(), requestConfirm, currentUser: Vue.ref({ username: 'test' }), hostCredentials: Vue.ref([]), loadHostCredentials: vi.fn() };
  const exports: any = {};
  const require = (path: string) => {
    if (path === 'vue') return { ...Vue, useId: () => `test-${scopes.length}`, onMounted: (fn: () => unknown) => mounted.push(fn), onUnmounted: vi.fn() };
    if (path === 'element-plus') return { ElMessage: { error: vi.fn(), success: vi.fn() }, ElMessageBox: { confirm, prompt: vi.fn().mockResolvedValue({ value: 'query' }) } };
    if (path === '@vue-flow/core') return { MarkerType: { ArrowClosed: 'arrowclosed' }, Position: { Left: 'left', Right: 'right' }, useVueFlow: () => ({ fitView: vi.fn().mockResolvedValue(true), setCenter: vi.fn(), viewport: Vue.ref({ zoom: 1 }), onNodesInitialized: vi.fn() }) };
    if (path === '@vue-flow/background' || path === '@vue-flow/controls' || path === '@vue-flow/minimap') return {};
    if (path === '@app/context') return { useAppContext: () => context };
    if (path.endsWith('/databaseManagement')) return api;
    if (path.endsWith('/errors')) return { errorMessage: (error: unknown) => String(error) };
    if (path.endsWith('/databaseDiagram')) return diagramUtils;
    if (path.endsWith('/mysqlConnection')) return connectionUtils;
    if (path.endsWith('/useDatabaseObjectActions')) return { useDatabaseObjectActions: () => ({ executeObjectAction: vi.fn() }) };
    return {};
  };
  const js = ts.transpileModule(script.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  new Function('require', 'exports', 'window', 'CustomEvent', js)(require, exports, { dispatchEvent: event, confirm: () => true }, class { constructor(public type: string, public init: unknown) {} });
  const scope = Vue.effectScope(); scopes.push(scope);
  const state: any = scope.run(() => exports.default.setup(props, { expose: vi.fn(), emit }));
  return { state, api, emit, confirm, requestConfirm, event, mounted };
}
const asset = { id: 7, name: 'mysql', dbType: 'mysql', databaseName: 'other', options: {} };
describe('MySQL workspace behavior', () => {
  it('opens independent documents, retains drafts while switching, and closes only the target database', async () => {
    const { state } = setup('DatabaseManagementPanel');
    state.assets.value = [asset];
    for (const type of ['query', 'table', 'er', 'accounts']) state.openDatabaseDocument(asset, 'tele', '', type);
    state.openDatabaseDocument(asset, 'other', '', 'query');
    const documents = state.documentTabs.value;
    expect(new Set(documents.map((d: any) => d.id)).size).toBe(5);
    state.dirtyDocuments.value[documents[0].id] = true;
    await state.activateWorkspaceTab(documents[0].id);
    await state.activateWorkspaceTab(documents[4].id);
    expect(state.dirtyDocuments.value[documents[0].id]).toBe(true);
    state.closeDatabaseDocuments(asset.id, 'tele');
    expect(state.documentTabs.value.map((d: any) => d.database)).toEqual(['other']);
    expect(state.activeWorkspaceTabId.value).toBe(documents[4].id);
  });
  it('routes menu actions using clicked database and waits for delete confirmation', async () => {
    const { state, api, requestConfirm } = setup('DatabaseManagementPanel');
    state.assets.value = [asset]; state.selected.value = asset; state.activeDatabase.value = 'other';
    state.treeMenu.value = { kind: 'database', assetId: 7, name: 'tele', database: 'tele' };
    await state.runMenuAction('new-query');
    expect(state.documentTabs.value[0].database).toBe('tele');
    await state.runMenuAction('edit-database');
    expect(state.mysqlEditDatabase.value).toEqual({ assetId: 7, database: 'tele' });
    await state.runMenuAction('database-import');
    expect(state.mysqlImportDatabase.value.database).toBe('tele');
    await state.runMenuAction('delete-database');
    expect(api.databaseAdmin).not.toHaveBeenCalled();
    await requestConfirm.mock.calls[0][3]();
    expect(api.databaseAdmin).toHaveBeenCalledWith(7, 'delete', 'tele');
  });
  it('guards menu entry execution and dirty tab closing', async () => {
    const denied = setup('DatabaseManagementPanel', {}, false);
    denied.state.assets.value = [asset]; denied.state.treeMenu.value = { kind: 'database', assetId: 7, name: 'tele' };
    await denied.state.runMenuAction('new-query'); await denied.state.runMenuAction('delete-database');
    expect(denied.state.documentTabs.value).toHaveLength(0); expect(denied.requestConfirm).not.toHaveBeenCalled();
    const { state, requestConfirm } = setup('DatabaseManagementPanel');
    state.assets.value = [asset]; state.openDatabaseDocument(asset, 'tele', '', 'table');
    state.closeWorkspaceTab(state.activeWorkspaceTabId.value);
    expect(state.documentTabs.value).toHaveLength(1);
    await requestConfirm.mock.calls[0][3](); expect(state.documentTabs.value).toHaveLength(0);
  });
  it('keeps query drafts independent and confirms mutating SQL', async () => {
    const first = setup('DatabaseWorkspaceDocument', { asset, document: { documentType: 'query', database: 'tele' } });
    const second = setup('DatabaseWorkspaceDocument', { asset, document: { documentType: 'query', database: 'other' } });
    first.state.sqlText.value = 'SELECT 1'; second.state.sqlText.value = 'SELECT 2';
    await first.state.run(); expect(first.api.executeDatabaseSql).toHaveBeenCalledWith(7, 'SELECT 1', 'tele', expect.any(AbortSignal));
    expect(second.state.sqlText.value).toBe('SELECT 2');
    first.state.sqlText.value = 'DELETE FROM sample'; first.confirm.mockRejectedValueOnce('cancel');
    await first.state.run(); expect(first.api.executeDatabaseSql).toHaveBeenCalledTimes(1);
  });
  it('requires a valid SQL file and preserves import options before dispatching', () => {
    const { state, event } = setup('DatabaseImportDialog', { assetId: 7, database: 'tele', schema: '' });
    state.selectFile({ target: { files: [] } }); state.upload(); expect(event).not.toHaveBeenCalled();
    state.selectFile({ target: { files: [{ name: 'bad.csv', size: 10 }], value: 'bad.csv' } }); state.upload(); expect(event).not.toHaveBeenCalled();
    state.selectFile({ target: { files: [{ name: 'ok.SQL', size: 10 }] } }); state.continueOnError.value = true; state.upload();
    expect(event.mock.calls[0][0].init.detail.target).toMatchObject({ database: 'tele', options: { continueOnError: true, asyncInsert: true } });
  });
  it('requires explicit import confirmation and sends cancellation to the same task', async () => {
    const task = { id: 'task-7', status: 'awaiting_confirmation', preview: { objects: [] } };
    const { state, api } = setup('DatabaseImportProgress', { tasks: [task] });
    state.taskId.value = task.id; await state.confirm(); expect(api.confirmDatabaseTransfer).not.toHaveBeenCalled();
    state.confirmed.value = true; state.policy.value = 'skip'; await state.confirm();
    expect(api.confirmDatabaseTransfer).toHaveBeenCalledWith(task.id, 'skip', true);
    await state.cancel(); expect(api.cancelDatabaseTransfer).toHaveBeenCalledWith(task.id);
  });
  it('filters collations and saves the selected charset pair to the captured target', async () => {
    const { state, api, mounted } = setup('MysqlDatabaseDialog', { assetId: 7, database: 'tele' });
    api.getMysqlMetadata.mockResolvedValue({ charset: 'utf8mb4', collation: 'utf8mb4_bin', choices: [{ charset: 'utf8mb4', collation: 'utf8mb4_bin' }, { charset: 'latin1', collation: 'latin1_bin' }] });
    await mounted[0](); state.charset.value = 'latin1'; state.changeCharset();
    expect(state.collation.value).toBe('latin1_bin'); expect(state.preview.value).toContain('ALTER DATABASE `tele` CHARACTER SET latin1 COLLATE latin1_bin');
    await state.save(); expect(api.editMysqlDatabase).toHaveBeenCalledWith(7, 'tele', 'latin1', 'latin1_bin');
  });
  it('builds primary keys, indexes and table options in the embedded editor', async () => {
    const { state, api, emit } = setup('DatabaseObjectEditor', { modelValue: true, embedded: true, context: { assetId: 7, database: 'tele', schema: '', dbType: 'mysql', mode: 'create', objectType: 'table', name: 'sample' } });
    state.columns.value.push({ name: 'code', type: 'VARCHAR(30)', nullable: true, primary: false, autoIncrement: false, defaultValue: "'abc'" });
    state.tableIndexes.value = [{ name: 'code_idx', columns: ['code'], unique: true }];
    state.comment.value = "owner's table";
    expect(state.tableDefinition.value).toContain('PRIMARY KEY (`id`)');
    expect(state.tableDefinition.value).toContain('UNIQUE KEY `code_idx` (`code`)');
    expect(state.tableDefinition.value).toContain("ENGINE=InnoDB COMMENT='owner''s table'");
    await state.save(); expect(api.runDatabaseObjectAction).toHaveBeenCalledWith(7, expect.objectContaining({ database: 'tele', name: 'sample' }));
    expect(emit).toHaveBeenCalledWith('saved'); expect(emit).not.toHaveBeenCalledWith('update:modelValue', false);
  });
  it('draws actual field relationships and changes only local diagram positions', async () => {
    const { state, api, mounted } = setup('DatabaseDiagram', { assetId: 7, database: 'tele' });
    api.getMysqlDiagram.mockResolvedValue({ columns: [{ table_name: 'orders', name: 'user_id' }, { table_name: 'users', name: 'id' }], relations: [{ source: 'orders', target: 'users', source_column: 'user_id', target_column: 'id' }] });
    await mounted[0]();
    expect(state.edges.value[0]).toMatchObject({ source: 'orders', target: 'users', sourceHandle: 'field-user_id', targetHandle: 'field-id' });
    const original = { ...state.nodes.value[0].position };
    state.nodes.value[0].position = { x: 42, y: 100 };
    state.focusTable('orders');
    expect(state.nodes.value[0]).toMatchObject({ selected: true, position: { x: 42, y: 100 } });
    state.arrange();
    expect(state.nodes.value[0].position).toEqual(original);
    expect(api.getMysqlDiagram).toHaveBeenCalledOnce();
    expect(api.runDatabaseObjectAction).not.toHaveBeenCalled();
  });
});
