<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { ChevronDown, ChevronRight, Database, DatabaseZap, Download, Folder, FolderPlus, LayoutList, Link2, MoreHorizontal, Play, Plus, RefreshCw, Search, Table2, Trash2, Upload } from '@lucide/vue';
import { useAppContext } from '@app/context';
import { errorMessage } from '@shared/utils/errors';
import { compressSqlText, formatSqlText } from '../utils/sqlText';
import {
  commitDatabaseRows, createDatabaseAsset, deleteDatabaseAsset, deleteRedisKey, executeDatabaseSql, exportDatabaseUrl, getDatabaseColumns,
  getDatabaseTableData, getDatabaseTree, getRedisKeys, getRedisValue, importDatabaseFile,
  getDatabaseIndexes, listDatabaseAssets, listDatabaseObjects, listDatabaseTypes, listSQLiteFiles, modifyDatabaseRow, modifyDatabaseSchema,
  runRedisCommand, testDatabaseAsset, updateDatabaseAsset, updateRedisKey,
  listAssetDirectories, createAssetDirectory, updateAssetDirectory, deleteAssetDirectory, copyAssetDirectory,
  copyDatabaseAsset, moveDatabaseAsset, connectionManifestUrl, importConnectionManifest, databaseAdmin, databaseExportUrl,
  type AssetDirectory, type ConnectionManifest, type DatabaseAsset, type DatabaseAssetPayload, type DatabaseColumn, type DatabaseIndex, type DatabaseTable, type DatabaseType,
} from '../api/databaseManagement';

type Tab = 'tables' | 'structure' | 'data' | 'sql' | 'transfer';
const { canUsePageAction, showToast, requestConfirm } = useAppContext();
const can = (action: string) => canUsePageAction('databaseManagement', action);
const assets = ref<DatabaseAsset[]>([]);
const directories = ref<AssetDirectory[]>([]);
const expandedDirectories = ref<number[]>([]);
const activeDirectoryId = ref<number | null>(null);
const directoryDialog = ref(false);
const directoryName = ref('');
const editingDirectory = ref<AssetDirectory | null>(null);
const moveDialog = ref(false);
const moving = ref<{ kind: 'asset' | 'directory'; id: number } | null>(null);
const moveTarget = ref<number | null>(null);
const configInput = ref<HTMLInputElement | null>(null);
const importDirectoryId = ref<number | null>(null);
const tableView = ref<'list' | 'table'>('list');
const objectSearch = ref('');
const objectSortAsc = ref(true);
const databaseDialog = ref(false);
const databaseAction = ref<'create' | 'delete' | 'clear' | 'import'>('create');
const databaseTarget = ref('');
const databaseInput = ref<HTMLInputElement | null>(null);
const types = ref<DatabaseType[]>([]);
const files = ref<string[]>([]);
const keyword = ref('');
const searchExpanded = ref(false);
const selected = ref<DatabaseAsset | null>(null);
const expandedAssets = ref<number[]>([]);
const expandedDatabase = ref('');
const expandedSchema = ref('');
const expandedCategory = ref<'table' | 'view' | 'procedure' | 'function' | ''>('');
const expandedQuery = ref(false);
const connected = ref(false);
const connecting = ref(false);
const createMenu = ref(false);
const dialog = ref(false);
const editing = ref<DatabaseAsset | null>(null);
const form = ref<DatabaseAssetPayload>(emptyForm('mysql'));
const databases = ref<string[]>([]);
const schemas = ref<string[]>([]);
const activeDatabase = ref('');
const schema = ref('');
const tables = ref<DatabaseTable[]>([]);
type ObjectCategory = 'table' | 'view' | 'procedure' | 'function';
const objectCategories: ObjectCategory[] = ['table', 'view', 'procedure', 'function'];
const objectCounts = ref<Record<ObjectCategory, number | null>>({ table: null, view: null, procedure: null, function: null });
let objectCountVersion = 0;
const objectCategory = ref<'table' | 'view' | 'procedure' | 'function'>('table');
const activeTable = ref('');
const columns = ref<DatabaseColumn[]>([]);
const indexes = ref<DatabaseIndex[]>([]);
const rows = ref<Record<string, unknown>[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(25);
const sort = ref('');
const direction = ref('asc');
const whereField = ref('');
const whereValue = ref('');
const selectedFields = ref<string[]>([]);
const transaction = ref(false);
const stagedChanges = ref<Record<string, unknown>[]>([]);
const loading = ref(false);
const tab = ref<Tab>('tables');
const sql = ref('');
const sqlRows = ref<Record<string, unknown>[]>([]);
const sqlMessage = ref('');
const sqlRunning = ref(false);
let sqlController: AbortController | null = null;
let sqlRequestVersion = 0;
let connectVersion = 0;
let workspaceVersion = 0;
let assetListVersion = 0;
const redisKeys = ref<{ key: string; type: string; ttl: number; size: number }[]>([]);
const redisDbCounts = ref<number[]>(Array(16).fill(0));
const redisDb = ref(0);
const redisPattern = ref('*');
const redisDetail = ref<{ key: string; type: string; ttl: number; value: unknown } | null>(null);
const redisCommand = ref('');
const redisResult = ref('');
const redisValueDraft = ref('');
const redisTtl = ref(-1);
const treeMenu = ref<{ x: number; y: number; kind: 'root' | 'directory' | 'asset' | 'database' | 'schema' | 'category' | 'object' | 'redis'; name: string; assetId?: number; directoryId?: number } | null>(null);
const menuSubmenu = ref('');
const importInput = ref<HTMLInputElement | null>(null);
const editingRow = ref<Record<string, unknown> | null>(null);
const originalRowKey = ref<Record<string, unknown>>({});
const rowDialog = ref(false);
const schemaDialog = ref(false);
const schemaAction = ref<'add_column' | 'drop_column' | 'create_index' | 'drop_index'>('add_column');
const schemaForm = ref({ name: '', columnType: 'TEXT', columns: [] as string[], unique: false });
const editMode = ref<'insert' | 'update'>('insert');
const activeType = computed(() => types.value.find(item => item.key === form.value.dbType));
const isRedis = computed(() => selected.value?.dbType === 'redis');
const allDataColumns = computed(() => columns.value.length ? columns.value.map(item => item.name) : Object.keys(rows.value[0] || {}));
const tableDataColumns = computed(() => selectedFields.value.length ? selectedFields.value : allDataColumns.value);
type CatalogEntry = { key: string; depth: number; directory?: AssetDirectory; asset?: DatabaseAsset };
const catalogEntries = computed<CatalogEntry[]>(() => {
  const result: CatalogEntry[] = [];
  const add = (parentId: number | null, depth: number) => {
    directories.value.filter(item => item.parentId === parentId).sort((a, b) => a.name.localeCompare(b.name)).forEach(folder => {
      result.push({ key: `folder-${folder.id}`, depth, directory: folder });
      if (expandedDirectories.value.includes(folder.id) || keyword.value) add(folder.id, depth + 1);
    });
    assets.value.filter(item => item.directoryId === parentId).sort((a, b) => a.name.localeCompare(b.name)).forEach(asset => {
      result.push({ key: `asset-${asset.id}`, depth, asset });
    });
  };
  add(null, 0);
  return result;
});
const visibleTables = computed(() => tables.value.filter(item => item.name.toLowerCase().includes(objectSearch.value.toLowerCase())).sort((a, b) => objectSortAsc.value ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name)));

function isRedisType(dbType: string) { return dbType.toLowerCase() === 'redis'; }
function toggleSearch() {
  searchExpanded.value = !searchExpanded.value;
  if (!searchExpanded.value) keyword.value = '';
}
function toggleAsset(asset: DatabaseAsset) {
  if (connecting.value) return;
  if (selected.value?.id === asset.id && connected.value) {
    expandedAssets.value = expandedAssets.value.includes(asset.id) ? expandedAssets.value.filter(id => id !== asset.id) : [...expandedAssets.value, asset.id];
    return;
  }
  void connectAsset(asset);
}
function toggleDatabase(name: string) {
  if (expandedDatabase.value === name) {
    expandedDatabase.value = '';
    return;
  }
  void selectDatabase(name);
}
function toggleSchema(name: string) {
  if (expandedSchema.value === name) {
    expandedSchema.value = '';
    expandedCategory.value = '';
    expandedQuery.value = false;
    return;
  }
  void selectSchema(name);
}
function toggleCategory(category: 'table' | 'view' | 'procedure' | 'function') {
  if (expandedCategory.value === category) {
    expandedCategory.value = '';
    return;
  }
  selectCategory(category);
}
function toggleQuery() {
  expandedQuery.value = !expandedQuery.value;
  if (expandedQuery.value) tab.value = 'sql';
}

function emptyForm(kind: string): DatabaseAssetPayload {
  const defaults: Record<string, number> = { mysql: 3306, mariadb: 3306, postgresql: 5432, kingbase: 54321, sqlserver: 1433, sqlite: 0, redis: 6379, clickhouse: 8123, oracle: 1521, dameng: 5236 };
  return { name: '', dbType: kind, host: kind === 'sqlite' ? '' : '127.0.0.1', port: types.value?.find(item => item.key === kind)?.defaultPort || defaults[kind] || 0, username: '', password: '', databaseName: '', remark: '', options: kind === 'redis' ? { db: 0 } : {} };
}
async function loadAssets() {
  if (!can('view')) return;
  const version = ++assetListVersion;
  try { const result = await listDatabaseAssets(keyword.value); if (version === assetListVersion) assets.value = result; }
  catch (error) { showToast('加载资产失败', errorMessage(error)); }
}
async function loadDirectories() {
  if (!can('view')) return;
  try { directories.value = await listAssetDirectories(); }
  catch (error) { showToast('加载资产目录失败', errorMessage(error)); }
}
async function refreshCatalog() { await Promise.all([loadAssets(), loadDirectories()]); }
function toggleDirectory(id: number) {
  expandedDirectories.value = expandedDirectories.value.includes(id) ? expandedDirectories.value.filter(value => value !== id) : [...expandedDirectories.value, id];
  activeDirectoryId.value = id;
}
function openDirectory(parentId: number | null, folder?: AssetDirectory) {
  editingDirectory.value = folder || null;
  activeDirectoryId.value = parentId;
  directoryName.value = folder?.name || '';
  directoryDialog.value = true;
}
async function saveDirectory() {
  try {
    if (editingDirectory.value) await updateAssetDirectory(editingDirectory.value.id, { name: directoryName.value });
    else await createAssetDirectory(directoryName.value, activeDirectoryId.value);
    directoryDialog.value = false;
    if (activeDirectoryId.value && !expandedDirectories.value.includes(activeDirectoryId.value)) expandedDirectories.value.push(activeDirectoryId.value);
    await loadDirectories();
  } catch (error) { showToast('保存目录失败', errorMessage(error)); }
}
function removeDirectory(folder: AssetDirectory) {
  requestConfirm('删除资产目录', `确定删除“${folder.name}”及其子目录和连接资产吗？`, '删除', async () => {
    try {
      await deleteAssetDirectory(folder.id);
      await refreshCatalog();
      if (selected.value && !assets.value.some(item => item.id === selected.value?.id)) { selected.value = null; resetWorkspace(); }
    } catch (error) { showToast('删除目录失败', errorMessage(error)); }
  });
}
function openMove(kind: 'asset' | 'directory', id: number) {
  moving.value = { kind, id }; moveTarget.value = null; moveDialog.value = true;
}
async function saveMove() {
  if (!moving.value) return;
  try {
    if (moving.value.kind === 'asset') await moveDatabaseAsset(moving.value.id, moveTarget.value);
    else await updateAssetDirectory(moving.value.id, { parentId: moveTarget.value });
    moveDialog.value = false; await refreshCatalog();
  } catch (error) { showToast('移动失败', errorMessage(error)); }
}
function dragItem(event: DragEvent, kind: 'asset' | 'directory', id: number) {
  event.dataTransfer?.setData('text/plain', JSON.stringify({ kind, id }));
}
async function dropItem(event: DragEvent, directoryId: number | null) {
  event.preventDefault();
  try {
    const item = JSON.parse(event.dataTransfer?.getData('text/plain') || '{}') as { kind: string; id: number };
    if (item.kind === 'asset') await moveDatabaseAsset(item.id, directoryId);
    else if (item.kind === 'directory') await updateAssetDirectory(item.id, { parentId: directoryId });
    else return;
    await refreshCatalog();
  } catch (error) { showToast('移动失败', errorMessage(error)); }
}
async function copyAsset(asset: DatabaseAsset, edit: boolean) {
  try {
    const result = await copyDatabaseAsset(asset.id);
    await loadAssets();
    if (edit) openEdit(result);
    else showToast('资产已克隆', result.name);
  } catch (error) { showToast('复制资产失败', errorMessage(error)); }
}
async function copyDirectory(folder: AssetDirectory) {
  try { await copyAssetDirectory(folder.id, folder.parentId); await refreshCatalog(); }
  catch (error) { showToast('复制目录失败', errorMessage(error)); }
}
async function downloadResponse(response: Response, filename: string) {
  if (!response.ok) throw new Error((await response.json()).error || '下载失败');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function exportConnections(directoryId: number | null, assetId?: number) {
  try { await downloadResponse(await fetch(connectionManifestUrl(directoryId, assetId), { credentials: 'include' }), 'database-connections.json'); }
  catch (error) { showToast('导出连接失败', errorMessage(error)); }
}
function chooseConnectionImport(directoryId: number | null) { importDirectoryId.value = directoryId; configInput.value?.click(); }
async function onConnectionImport(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0]; if (!file) return;
  try {
    if (file.size > 5_000_000) throw new Error('连接配置文件不能超过 5 MB');
    const manifest = JSON.parse(await file.text()) as ConnectionManifest;
    await importConnectionManifest(manifest, importDirectoryId.value);
    await refreshCatalog(); showToast('连接已导入', '请编辑连接补充密码');
  } catch (error) { showToast('导入连接失败', errorMessage(error)); }
  input.value = '';
}
function openDatabaseAction(action: typeof databaseAction.value, name = '') {
  if (!selected.value) return;
  databaseAction.value = action;
  databaseTarget.value = name || activeDatabase.value || (selected.value.dbType === 'sqlite' ? String(selected.value.options.file || '') : selected.value.dbType === 'redis' ? String(selected.value.options.db || 0) : '');
  databaseDialog.value = true;
}
function databaseNodeName(item: NonNullable<typeof treeMenu.value>) {
  if (selected.value?.dbType === 'sqlite') return String(selected.value.options.file || '');
  return item.name;
}
async function saveDatabaseAction() {
  if (!selected.value) return;
  const assetId = selected.value.id, action = databaseAction.value, name = databaseTarget.value.trim();
  const execute = async () => {
    try {
      if (action === 'import') { databaseInput.value?.click(); return; }
      await databaseAdmin(assetId, action, name);
      databaseDialog.value = false;
      if (action === 'delete' || action === 'clear') { resetWorkspace(); selected.value = null; }
      else await connectAsset(selected.value!);
      showToast('数据库操作完成', `${action} · ${name}`);
    } catch (error) { showToast('数据库操作失败', errorMessage(error)); }
  };
  if (action === 'delete' || action === 'clear') requestConfirm('确认数据库操作', `确定对“${name}”执行${action === 'delete' ? '删除' : '清空'}吗？`, '确认', execute);
  else await execute();
}
async function onDatabaseImport(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0];
  if (!file || !selected.value) return;
  try {
    if (file.size > 5_000_000) throw new Error('数据包不能超过 5 MB');
    const snapshot = JSON.parse(await file.text());
    await databaseAdmin(selected.value.id, 'import', databaseTarget.value.trim(), snapshot);
    databaseDialog.value = false; await loadObjects(); showToast('数据库导入完成', file.name);
  } catch (error) { showToast('数据库导入失败', errorMessage(error)); }
  input.value = '';
}
async function exportDatabase(name: string) {
  if (!selected.value) return;
  try { await downloadResponse(await fetch(databaseExportUrl(selected.value.id, name), { credentials: 'include' }), 'database-export.json'); }
  catch (error) { showToast('数据库导出失败', errorMessage(error)); }
}
function resetWorkspace() {
  workspaceVersion++;
  resetObjectCounts();
  expandedAssets.value = [];
  expandedDatabase.value = '';
  expandedSchema.value = '';
  expandedCategory.value = '';
  expandedQuery.value = false;
  connected.value = false; databases.value = []; schemas.value = []; activeDatabase.value = ''; schema.value = '';
  tables.value = []; objectCategory.value = 'table'; activeTable.value = ''; columns.value = []; indexes.value = []; rows.value = []; total.value = 0;
  sql.value = ''; sqlRows.value = []; sqlMessage.value = ''; redisKeys.value = []; redisDetail.value = null;
  redisValueDraft.value = ''; redisResult.value = ''; redisPattern.value = '*'; tab.value = 'tables';
  redisDb.value = 0; redisDbCounts.value = Array(16).fill(0);
  transaction.value = false; stagedChanges.value = []; selectedFields.value = []; whereField.value = ''; whereValue.value = '';
  sort.value = ''; direction.value = 'asc'; page.value = 1; loading.value = false;
  sqlRequestVersion++; sqlController?.abort(); sqlController = null; sqlRunning.value = false;
}
function openCreate(kind: string) { editing.value = null; form.value = { ...emptyForm(kind), directoryId: activeDirectoryId.value }; createMenu.value = false; dialog.value = true; }
function openEdit(asset: DatabaseAsset) { editing.value = asset; form.value = { ...asset, password: '', options: { ...asset.options } }; dialog.value = true; }
async function saveAsset() {
  try {
    const payload = { ...form.value };
    if (editing.value && !payload.password) delete payload.password;
    if (editing.value) await updateDatabaseAsset(editing.value.id, payload);
    else await createDatabaseAsset(payload);
    dialog.value = false; await loadAssets(); showToast('已保存', '连接资产已保存');
  } catch (error) { showToast('保存失败', errorMessage(error)); }
}
async function connectAsset(asset: DatabaseAsset) {
  if (stagedChanges.value.length) {
    requestConfirm('切换连接资产', '当前暂存修改尚未提交，切换后会丢弃，确定继续吗？', '切换', async () => { stagedChanges.value = []; await connectAsset(asset); });
    return;
  }
  const version = ++connectVersion;
  selected.value = asset; resetWorkspace(); connecting.value = true;
  expandedAssets.value = [asset.id];
  try {
    await testDatabaseAsset(asset.id);
    if (version !== connectVersion) return;
    connected.value = true;
    if (asset.dbType === 'redis') { const configuredDb = Number(asset.options.db || 0); await loadRedis(configuredDb < 16 ? configuredDb : 0); return; }
    databases.value = (await getDatabaseTree(asset.id)).databases;
    if (version !== connectVersion) return;
    activeDatabase.value = asset.databaseName || databases.value[0] || '';
    await selectDatabase(activeDatabase.value);
  } catch (error) { if (version === connectVersion) { connected.value = false; expandedAssets.value = expandedAssets.value.filter(id => id !== asset.id); showToast('连接失败', errorMessage(error)); } }
  finally { if (version === connectVersion) connecting.value = false; }
}
async function selectDatabase(name: string) {
  if (!selected.value) return;
  if (activeDatabase.value !== name && stagedChanges.value.length) {
    requestConfirm('切换数据库', '当前暂存修改尚未提交，切换后会丢弃，确定继续吗？', '切换', async () => { stagedChanges.value = []; await selectDatabase(name); });
    return;
  }
  const version = ++workspaceVersion;
  resetObjectCounts();
  const assetId = selected.value.id;
  activeDatabase.value = name; schema.value = ''; activeTable.value = ''; tables.value = []; rows.value = []; columns.value = []; indexes.value = [];
  expandedDatabase.value = name;
  expandedSchema.value = '';
  expandedCategory.value = '';
  expandedQuery.value = false;
  try {
    const result = await getDatabaseTree(assetId, name);
    if (version !== workspaceVersion || selected.value?.id !== assetId || activeDatabase.value !== name) return;
    schemas.value = result.schemas;
    schema.value = schemas.value.find(item => item === String(selected.value?.options.schema || '')) || schemas.value[0] || '';
    if (!schemas.value.length) void loadObjectCounts();
    await loadObjects();
  } catch (error) { showToast('加载数据库失败', errorMessage(error)); }
}
async function selectSchema(name: string) {
  if (schema.value !== name && stagedChanges.value.length) {
    requestConfirm('切换 Schema', '当前暂存修改尚未提交，切换后会丢弃，确定继续吗？', '切换', async () => { stagedChanges.value = []; await selectSchema(name); });
    return;
  }
  resetObjectCounts();
  schema.value = name; expandedSchema.value = name; expandedCategory.value = ''; expandedQuery.value = false;
  void loadObjectCounts();
  await loadObjects();
}
function resetObjectCounts() {
  objectCountVersion++;
  objectCounts.value = { table: null, view: null, procedure: null, function: null };
}
async function loadObjectCounts() {
  if (!selected.value || !connected.value) return;
  const version = ++objectCountVersion;
  const assetId = selected.value.id, database = activeDatabase.value, owner = schema.value;
  const results = await Promise.allSettled(objectCategories.map(category => listDatabaseObjects(assetId, database, owner || undefined, category)));
  if (version !== objectCountVersion || selected.value?.id !== assetId || activeDatabase.value !== database || schema.value !== owner) return;
  const counts = { ...objectCounts.value };
  objectCategories.forEach((category, index) => { counts[category] = results[index].status === 'fulfilled' ? results[index].value.objects.length : null; });
  objectCounts.value = counts;
}
async function loadObjects() {
  if (!selected.value || !connected.value) return;
  const version = ++workspaceVersion;
  const assetId = selected.value.id, database = activeDatabase.value, owner = schema.value, category = objectCategory.value;
  tables.value = []; activeTable.value = ''; rows.value = []; columns.value = []; indexes.value = []; total.value = 0; tab.value = 'tables';
  try {
    const result = await listDatabaseObjects(assetId, database, owner || undefined, category);
    if (version !== workspaceVersion || selected.value?.id !== assetId || activeDatabase.value !== database || schema.value !== owner || objectCategory.value !== category) return;
    tables.value = result.objects;
    objectCounts.value = { ...objectCounts.value, [category]: result.objects.length };
  }
  catch (error) { showToast('加载对象失败', errorMessage(error)); }
}
async function selectTable(name: string) {
  if (!selected.value) return;
  if (activeTable.value !== name && stagedChanges.value.length) {
    requestConfirm('切换数据表', '当前暂存修改尚未提交，切换后会丢弃，确定继续吗？', '切换', async () => { stagedChanges.value = []; await selectTable(name); });
    return;
  }
  const version = ++workspaceVersion;
  const assetId = selected.value.id, database = activeDatabase.value, owner = schema.value;
  if (objectCategory.value === 'procedure' || objectCategory.value === 'function') { activeTable.value = name; tab.value = 'structure'; columns.value = []; return; }
  activeTable.value = name; tab.value = 'data'; page.value = 1; selectedFields.value = []; stagedChanges.value = [];
  try { const [columnResult, indexResult] = await Promise.all([getDatabaseColumns(assetId, database, name, owner || undefined), getDatabaseIndexes(assetId, database, name, owner || undefined)]); if (version !== workspaceVersion || selected.value?.id !== assetId || activeTable.value !== name) return; columns.value = columnResult.columns; indexes.value = indexResult.indexes; await loadData(); }
  catch (error) { showToast('读取表失败', errorMessage(error)); }
}
function selectCategory(category: 'table' | 'view' | 'procedure' | 'function') {
  if (objectCategory.value !== category && stagedChanges.value.length) {
    requestConfirm('切换对象类别', '当前暂存修改尚未提交，切换后会丢弃，确定继续吗？', '切换', async () => { stagedChanges.value = []; selectCategory(category); });
    return;
  }
  expandedCategory.value = category;
  expandedQuery.value = false;
  objectCategory.value = category; void loadObjects();
}
function openTreeMenu(event: MouseEvent, kind: NonNullable<typeof treeMenu.value>['kind'], name: string, assetId?: number, directoryId?: number) {
  treeMenu.value = { x: Math.max(8, Math.min(event.clientX, window.innerWidth - 225)), y: Math.max(8, Math.min(event.clientY, window.innerHeight - 370)), kind, name, assetId, directoryId };
  menuSubmenu.value = '';
}
type MenuAction = { id: string; label: string; children?: MenuAction[] };
const menuActions = computed<MenuAction[]>(() => {
  const item = treeMenu.value; if (!item) return [];
  if (item.kind === 'root' || item.kind === 'directory') return [
    ...(can('create') ? [{ id: 'new-folder', label: '新建目录' }, { id: 'new-connection', label: '新建连接' }] : []),
    ...(item.kind === 'directory' && can('edit') ? [{ id: 'rename-folder', label: '重命名' }, { id: 'move-folder', label: '移动目录' }] : []),
    ...(item.kind === 'directory' && can('create') ? [{ id: 'copy-folder', label: '复制目录' }] : []),
    ...(can('import_export') ? [{ id: 'import-connections', label: '导入连接' }, { id: 'export-connections', label: '导出连接' }] : []),
    ...(item.kind === 'directory' && can('delete') ? [{ id: 'delete-folder', label: '删除目录' }] : []),
    { id: 'refresh', label: '刷新' },
  ];
  if (item.kind === 'asset') return [
    { id: 'open', label: '连接 / 刷新' },
    ...(can('test_connection') ? [{ id: 'test', label: '测试连接' }] : []),
    ...(connected.value && selected.value?.id === item.assetId ? [{ id: 'disconnect', label: '断开' }] : []),
    ...(can('edit') ? [{ id: 'edit', label: '编辑' }, { id: 'move-asset', label: '移动' }] : []),
    ...(can('create') ? [{ id: 'copy-host', label: '复制 Host' }, { id: 'clone', label: '克隆' }] : []),
    ...(can('import_export') ? [{ id: 'export-connections', label: '导出连接' }] : []),
    ...(can('delete') ? [{ id: 'delete-asset', label: '删除' }] : []),
  ];
  if (item.kind === 'database') return [
    { id: 'open', label: '打开' }, { id: 'refresh', label: '刷新' },
    ...(can('database_admin') ? [{ id: 'database-ops', label: '数据库操作', children: [
      { id: 'database-create', label: '新建数据库' }, { id: 'database-import', label: '导入数据库' },
      { id: 'database-export', label: '导出数据库' }, { id: 'database-clear', label: '清空数据库' }, { id: 'database-delete', label: '删除数据库' },
    ] }] : []),
  ];
  return [{ id: 'open', label: '打开' }, { id: 'refresh', label: '刷新' }];
});
async function runMenuAction(action: string) {
  const item = treeMenu.value;
  treeMenu.value = null; menuSubmenu.value = '';
  if (!item) return;
  if (action === 'refresh' && (item.kind === 'root' || item.kind === 'directory')) { await refreshCatalog(); return; }
  if (action === 'open' || action === 'refresh' || action === 'disconnect') { treeMenu.value = item; await runTreeAction(action); return; }
  const asset = assets.value.find(value => value.id === item.assetId);
  const folder = directories.value.find(value => value.id === item.directoryId);
  if (action === 'new-folder') { openDirectory(item.kind === 'directory' ? item.directoryId! : null); return; }
  if (action === 'new-connection') { activeDirectoryId.value = item.kind === 'directory' ? item.directoryId! : null; createMenu.value = true; return; }
  if (action === 'rename-folder' && folder) { openDirectory(folder.parentId, folder); return; }
  if (action === 'move-folder' && folder) { openMove('directory', folder.id); return; }
  if (action === 'copy-folder' && folder) { await copyDirectory(folder); return; }
  if (action === 'delete-folder' && folder) { removeDirectory(folder); return; }
  if (action === 'import-connections') { chooseConnectionImport(folder?.id || null); return; }
  if (action === 'export-connections') { await exportConnections(item.kind === 'asset' ? asset?.directoryId || null : folder?.id || null, item.kind === 'asset' ? asset?.id : undefined); return; }
  if (action === 'test' && asset) {
    try { await testDatabaseAsset(asset.id); showToast('连接成功', asset.name); }
    catch (error) { showToast('连接失败', errorMessage(error)); }
    return;
  }
  if (action === 'edit' && asset) { openEdit(asset); return; }
  if (action === 'move-asset' && asset) { openMove('asset', asset.id); return; }
  if (action === 'copy-host' && asset) { await copyAsset(asset, true); return; }
  if (action === 'clone' && asset) { await copyAsset(asset, false); return; }
  if (action === 'delete-asset' && asset) { removeAsset(asset); return; }
  if (action.startsWith('database-') && selected.value) {
    const targetName = databaseNodeName(item);
    if (action === 'database-export') await exportDatabase(targetName);
    else openDatabaseAction(action.slice('database-'.length) as typeof databaseAction.value, targetName);
  }
}
async function runTreeAction(action: 'open' | 'refresh' | 'disconnect') {
  const item = treeMenu.value;
  treeMenu.value = null;
  if (!item) return;
  if (action === 'disconnect') { connectVersion++; resetWorkspace(); return; }
  if (item.kind === 'asset') { const asset = assets.value.find(value => value.id === item.assetId); if (asset) await connectAsset(asset); return; }
  if (!selected.value) return;
  if (item.kind === 'database') { if (isRedis.value) await selectRedisDatabase(Number(item.name)); else await selectDatabase(item.name); return; }
  if (item.kind === 'schema') { await selectSchema(item.name); return; }
  if (item.kind === 'category') { selectCategory(item.name as 'table' | 'view' | 'procedure' | 'function'); return; }
  if (item.kind === 'object') { await selectTable(item.name); return; }
  if (item.kind === 'redis') { if (action === 'refresh') await loadRedis(); else await selectRedisKey(item.name); }
}
function openSchema(action: typeof schemaAction.value, item?: { name: string; columns?: string[]; unique?: boolean }) {
  schemaAction.value = action;
  schemaForm.value = { name: item?.name || '', columnType: 'TEXT', columns: item?.columns || [], unique: Boolean(item?.unique) };
  schemaDialog.value = true;
}
async function saveSchema() {
  if (!selected.value) return;
  const assetId = selected.value.id, table = activeTable.value, database = activeDatabase.value, owner = schema.value;
  const action = schemaAction.value, payload = { database, schema: owner, table, action, ...schemaForm.value };
  const execute = async () => {
    try {
      await modifyDatabaseSchema(assetId, payload);
      schemaDialog.value = false;
      const [columnResult, indexResult] = await Promise.all([getDatabaseColumns(assetId, database, table, owner || undefined), getDatabaseIndexes(assetId, database, table, owner || undefined)]);
      if (selected.value?.id === assetId && activeTable.value === table) { columns.value = columnResult.columns; indexes.value = indexResult.indexes; }
      showToast('结构已更新', '表结构已刷新');
    } catch (error) { showToast('结构操作失败', errorMessage(error)); }
  };
  if (action.startsWith('drop_')) requestConfirm('确认删除结构', `确定删除“${schemaForm.value.name}”吗？此操作无法撤销。`, '删除', execute);
  else await execute();
}
async function loadData() {
  if (!selected.value || !activeTable.value) return;
  const version = ++workspaceVersion;
  const assetId = selected.value.id, database = activeDatabase.value, table = activeTable.value;
  loading.value = true;
  try {
    const result = await getDatabaseTableData(assetId, { database, schema: schema.value, table, page: page.value, pageSize: pageSize.value, sort: sort.value, direction: direction.value, fields: selectedFields.value.join(','), whereField: whereField.value, whereValue: whereValue.value });
    if (version === workspaceVersion && selected.value?.id === assetId && activeDatabase.value === database && activeTable.value === table) { rows.value = result.rows; total.value = result.total; }
  } catch (error) { showToast('加载数据失败', errorMessage(error)); }
  finally { if (version === workspaceVersion) loading.value = false; }
}
async function runSql() {
  if (!selected.value || !sql.value.trim()) return;
  const asset = selected.value;
  const execute = async () => {
    const version = connectVersion, requestVersion = ++sqlRequestVersion;
    const controller = new AbortController();
    sqlRunning.value = true; sqlController = controller;
    try {
      const result = await executeDatabaseSql(asset.id, sql.value, activeDatabase.value, controller.signal);
      if (version === connectVersion && requestVersion === sqlRequestVersion && selected.value?.id === asset.id) {
        sqlRows.value = result.rows; sqlMessage.value = `${result.affected} 行 · ${result.elapsedMs} ms`;
      }
    } catch (error) { if ((error as Error).name !== 'AbortError') showToast('SQL 执行失败', errorMessage(error)); }
    finally { if (requestVersion === sqlRequestVersion) { sqlRunning.value = false; sqlController = null; } }
  };
  if (!/^\s*(select|show|describe|explain)\b/i.test(sql.value) || /\bINTO\s+(OUTFILE|DUMPFILE)\b/i.test(sql.value))
    requestConfirm('确认执行 SQL', '这条语句可能修改数据库内容，确定执行吗？', '执行', execute);
  else await execute();
}
function stopSql() { sqlRequestVersion++; sqlController?.abort(); sqlController = null; sqlRunning.value = false; sqlMessage.value = '已取消等待；服务器可能仍在执行'; }
function formatSql() { sql.value = formatSqlText(sql.value); }
function compressSql() { sql.value = compressSqlText(sql.value); }
function explainSql() { if (sql.value.trim()) { sql.value = `EXPLAIN ${sql.value.trim()}`; void runSql(); } }
function openRow(mode: 'insert' | 'update', row?: Record<string, unknown>) {
  if (mode === 'update' && selectedFields.value.length) { showToast('无法编辑', '请先显示全部字段再编辑数据行'); return; }
  editMode.value = mode; editingRow.value = mode === 'update' ? { ...row } : Object.fromEntries(columns.value.map(column => [column.name, '']));
  const keys = columns.value.filter(column => column.column_key === 'PRI').map(column => column.name);
  originalRowKey.value = mode === 'update' && row ? Object.fromEntries(keys.map(key => [key, row[key]])) : {};
  rowDialog.value = true;
}
async function saveRow() {
  if (!selected.value || !editingRow.value) return;
  if (editMode.value === 'update' && !Object.keys(originalRowKey.value).length) { showToast('无法编辑', '该表没有可用的主键'); return; }
  try {
    const values = { ...editingRow.value };
    const change = { schema: schema.value, table: activeTable.value, action: editMode.value, values, key: editMode.value === 'update' ? originalRowKey.value : {} };
    if (transaction.value) stagedChanges.value.push(change);
    else await modifyDatabaseRow(selected.value.id, { database: activeDatabase.value, ...change });
    rowDialog.value = false; if (!transaction.value) await loadData(); showToast('保存成功', transaction.value ? '修改已暂存' : '数据已更新');
  } catch (error) { showToast('保存失败', errorMessage(error)); }
}
function removeRow(row: Record<string, unknown>) {
  if (!selected.value) return;
  if (selectedFields.value.length) { showToast('无法删除', '请先显示全部字段再删除数据行'); return; }
  const keys = columns.value.filter(column => column.column_key === 'PRI').map(column => column.name);
  if (!keys.length) { showToast('无法删除', '该表没有主键'); return; }
  requestConfirm('删除数据行', '确定删除这条数据吗？', '删除', async () => {
    try {
      const change = { schema: schema.value, table: activeTable.value, action: 'delete', key: Object.fromEntries(keys.map(key => [key, row[key]])) };
      if (transaction.value) stagedChanges.value.push(change);
      else { await modifyDatabaseRow(selected.value!.id, { database: activeDatabase.value, ...change }); await loadData(); }
    }
    catch (error) { showToast('删除失败', errorMessage(error)); }
  });
}
async function commitRows() {
  if (!selected.value || !stagedChanges.value.length) return;
  try { await commitDatabaseRows(selected.value.id, { database: activeDatabase.value, changes: stagedChanges.value }); stagedChanges.value = []; transaction.value = false; await loadData(); showToast('提交成功', '暂存修改已提交'); }
  catch (error) { showToast('提交失败', errorMessage(error)); }
}
function rollbackRows() { stagedChanges.value = []; transaction.value = false; showToast('已回滚', '暂存修改已清除'); }
async function selectRedisDatabase(db: number) {
  redisKeys.value = []; redisDetail.value = null; redisPattern.value = '*';
  activeDatabase.value = String(db);
  await loadRedis(db);
}
async function loadRedis(db = redisDb.value) {
  if (!selected.value) return;
  const assetId = selected.value.id, version = workspaceVersion, pattern = redisPattern.value;
  redisDb.value = db;
  activeDatabase.value = String(db);
  try { const result = await getRedisKeys(assetId, pattern, db); if (version === workspaceVersion && selected.value?.id === assetId && redisPattern.value === pattern && redisDb.value === db) { redisKeys.value = result.keys; redisDbCounts.value = result.counts; } }
  catch (error) { showToast('读取 Redis 失败', errorMessage(error)); }
}
async function selectRedisKey(key: string) {
  if (!selected.value) return;
  const assetId = selected.value.id, version = workspaceVersion;
  const db = redisDb.value;
  try { const result = await getRedisValue(assetId, key, db); if (version !== workspaceVersion || selected.value?.id !== assetId || redisDb.value !== db) return; redisDetail.value = result; redisValueDraft.value = typeof result.value === 'string' ? result.value : JSON.stringify(result.value, null, 2); redisTtl.value = result.ttl; }
  catch (error) { showToast('读取键失败', errorMessage(error)); }
}
async function saveRedisValue() {
  if (!selected.value || !redisDetail.value) return;
  try {
    const value = redisDetail.value.type === 'string' ? redisValueDraft.value : JSON.parse(redisValueDraft.value);
    await updateRedisKey(selected.value.id, { action: 'set_value', key: redisDetail.value.key, value, db: redisDb.value });
    await selectRedisKey(redisDetail.value.key); await loadRedis();
  } catch (error) { showToast('保存键失败', errorMessage(error)); }
}
async function saveRedisTtl() {
  if (!selected.value || !redisDetail.value) return;
  try { await updateRedisKey(selected.value.id, { action: 'set_ttl', key: redisDetail.value.key, ttl: redisTtl.value, db: redisDb.value }); await selectRedisKey(redisDetail.value.key); await loadRedis(); }
  catch (error) { showToast('更新 TTL 失败', errorMessage(error)); }
}
function removeRedisKey() {
  if (!selected.value || !redisDetail.value) return;
  requestConfirm('删除 Redis 键', `确定删除“${redisDetail.value.key}”吗？`, '删除', async () => {
    try { await deleteRedisKey(selected.value!.id, redisDetail.value!.key, redisDb.value); redisDetail.value = null; await loadRedis(); }
    catch (error) { showToast('删除键失败', errorMessage(error)); }
  });
}
async function runRedis() {
  if (!selected.value) return;
  try { const result = await runRedisCommand(selected.value.id, redisCommand.value.trim().split(/\s+/), redisDb.value); redisResult.value = JSON.stringify(result.result, null, 2); await loadRedis(); }
  catch (error) { showToast('命令失败', errorMessage(error)); }
}
async function onImport(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file || !selected.value) return;
  const format = file.name.split('.').pop()?.toLowerCase() || 'csv';
  const body = new FormData(); body.set('file', file); body.set('format', format); body.set('database', activeDatabase.value); body.set('schema', schema.value); body.set('table', activeTable.value);
  try { const result = await importDatabaseFile(selected.value.id, body); showToast('导入完成', `已处理 ${result.imported} 条`); if (isRedis.value) await loadRedis(); else await loadData(); }
  catch (error) { showToast('导入失败', errorMessage(error)); }
  (event.target as HTMLInputElement).value = '';
}
async function exportFile(format: string) {
  if (!selected.value) return;
  try {
    const response = await fetch(exportDatabaseUrl(selected.value.id, { format, database: activeDatabase.value, schema: schema.value, table: activeTable.value }), { credentials: 'include' });
    if (!response.ok) { const payload = await response.json(); throw new Error(payload.error || payload.detail || '导出失败'); }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a'); link.href = url; link.download = `${selected.value.name}.${format}`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { showToast('导出失败', errorMessage(error)); }
}
function removeAsset(asset: DatabaseAsset) {
  requestConfirm('删除连接资产', `确定删除“${asset.name}”吗？`, '删除', async () => {
    try { await deleteDatabaseAsset(asset.id); if (selected.value?.id === asset.id) { selected.value = null; resetWorkspace(); } await loadAssets(); }
    catch (error) { showToast('删除失败', errorMessage(error)); }
  });
}
watch(keyword, () => { void loadAssets(); });
onMounted(() => {
  window.addEventListener('click', closeTreeMenu);
  void refreshCatalog();
  void listDatabaseTypes().then(result => { types.value = result.types; }).catch(error => showToast('加载数据库类型失败', errorMessage(error)));
  void listSQLiteFiles().then(result => { files.value = result.files; }).catch(error => showToast('加载 SQLite 文件失败', errorMessage(error)));
});
function closeTreeMenu() { treeMenu.value = null; }
onUnmounted(() => {
  objectCountVersion++;
  window.removeEventListener('click', closeTreeMenu);
  connectVersion++; workspaceVersion++; assetListVersion++; sqlRequestVersion++; sqlController?.abort();
});
</script>

<template>
  <div class="db-workspace">
    <aside class="db-sidebar">
      <header class="db-sidebar-head"><strong>资产列表</strong><div class="db-actions"><el-input v-if="searchExpanded" v-model="keyword" class="db-sidebar-search" placeholder="搜索资产" clearable @clear="searchExpanded = false" /><el-button text circle title="搜索资产" :class="{ active: searchExpanded }" @click="toggleSearch"><Search :size="15" /></el-button><el-button text circle title="刷新资产" @click="refreshCatalog"><RefreshCw :size="15" /></el-button><el-button v-if="can('create')" text circle title="导入连接配置" @click="chooseConnectionImport(activeDirectoryId)"><Download :size="15" /></el-button><el-button v-if="can('create')" text circle title="新建目录" @click="openDirectory(activeDirectoryId)"><FolderPlus :size="15" /></el-button><el-popover v-if="can('create')" v-model:visible="createMenu" placement="bottom-end" trigger="click" :width="190"><template #reference><el-button type="primary" circle title="链接数据库"><Link2 :size="15" /></el-button></template><button v-for="kind in types" :key="kind.key" class="db-type-option" @click="openCreate(kind.key)"><Database :size="15" />{{ kind.label }}</button></el-popover></div></header>
      <div class="db-asset-scroll" @dragover.prevent @drop="dropItem($event, null)" @contextmenu.prevent="openTreeMenu($event, 'root', '根目录')">
        <div class="db-catalog-root" @click="activeDirectoryId = null" @contextmenu.stop.prevent="openTreeMenu($event, 'root', '根目录')"><Folder :size="15" /><span>根目录</span></div>
        <div v-if="!catalogEntries.length" class="db-empty">暂无连接资产</div>
        <div v-for="entry in catalogEntries" :key="entry.key" class="db-catalog-entry" :style="{ paddingLeft: `${10 + entry.depth * 12}px` }" draggable="true" @dragstart="dragItem($event, entry.directory ? 'directory' : 'asset', entry.directory?.id || entry.asset!.id)" @dragover.prevent @drop.stop="entry.directory && dropItem($event, entry.directory.id)" @contextmenu.stop.prevent="entry.directory ? openTreeMenu($event, 'directory', entry.directory.name, undefined, entry.directory.id) : openTreeMenu($event, 'asset', entry.asset!.name, entry.asset!.id, entry.asset!.directoryId || undefined)">
          <template v-if="entry.directory"><div class="db-catalog-row"><button class="db-tree-toggle" @click.stop="toggleDirectory(entry.directory.id)"><ChevronDown v-if="expandedDirectories.includes(entry.directory.id)" :size="14" /><ChevronRight v-else :size="14" /></button><Folder class="db-folder-icon" :size="15" /><button class="db-catalog-label" @click="toggleDirectory(entry.directory.id)">{{ entry.directory.name }}</button></div></template>
          <template v-else><div class="db-catalog-row" :class="{ active: selected?.id === entry.asset!.id }"><button class="db-tree-toggle" @click.stop="toggleAsset(entry.asset!)"><ChevronDown v-if="selected?.id === entry.asset!.id && connected && expandedAssets.includes(entry.asset!.id)" :size="14" /><ChevronRight v-else :size="14" /></button><DatabaseZap v-if="isRedisType(entry.asset!.dbType)" class="db-asset-icon redis" :size="15" /><Database v-else class="db-asset-icon" :size="15" /><button class="db-catalog-label" :class="{ active: selected?.id === entry.asset!.id }" @click="toggleAsset(entry.asset!)"><span>{{ entry.asset!.name }}</span><small>{{ selected?.id === entry.asset!.id && connected ? '已连接' : '未连接' }} · {{ entry.asset!.dbType }}</small></button><button class="db-asset-more" title="资产操作" @click.stop="openTreeMenu($event, 'asset', entry.asset!.name, entry.asset!.id, entry.asset!.directoryId || undefined)"><MoreHorizontal :size="15" /></button></div>
            <div v-if="selected?.id === entry.asset!.id && connected && expandedAssets.includes(entry.asset!.id)" class="db-asset-children">
              <template v-if="isRedisType(entry.asset!.dbType)">
                <div v-for="db in 16" :key="db" class="db-tree-row db-redis-db-row" :class="{ active: redisDb === db - 1 }" @contextmenu.stop.prevent="openTreeMenu($event, 'database', String(db - 1))">
                  <Database class="db-tree-database-icon" :size="15" />
                  <button class="db-tree-label" @click="selectRedisDatabase(db - 1)"><span>db{{ db - 1 }}</span><small class="db-tree-count">{{ redisDbCounts[db - 1] }}</small></button>
                </div>
              </template>
              <template v-else>
                <div class="db-tree-level db-database-level">
                  <div v-for="name in databases" :key="name" class="db-tree-item">
                    <div class="db-tree-row" :class="{ active: activeDatabase === name }">
                      <button class="db-tree-toggle" @click.stop="toggleDatabase(name)"><ChevronDown v-if="expandedDatabase === name" :size="13" /><ChevronRight v-else :size="13" /></button>
                      <Database class="db-tree-database-icon" :size="15" />
                      <button class="db-tree-label" @click="toggleDatabase(name)">{{ name }}</button>
                    </div>
                    <div v-if="expandedDatabase === name" class="db-tree-children">
                      <div v-for="item in (schemas.length ? schemas : [''])" :key="item || '__default-schema__'" class="db-tree-item">
                        <div v-if="item" class="db-tree-row" :class="{ active: expandedSchema === item }">
                          <button class="db-tree-toggle" @click.stop="toggleSchema(item)"><ChevronDown v-if="expandedSchema === item" :size="13" /><ChevronRight v-else :size="13" /></button>
                          <Database class="db-tree-schema-icon" :size="14" />
                          <button class="db-tree-label" @click="toggleSchema(item)">{{ item }}</button>
                        </div>
                        <div v-if="expandedSchema === item || (!schemas.length && expandedDatabase === name)" class="db-tree-children db-object-level" :class="{ 'db-object-level-flat': !item }">
                          <div v-for="category in [{ key: 'table', label: '表' }, { key: 'view', label: '视图' }, { key: 'procedure', label: '存储过程' }, { key: 'function', label: '函数' }]" :key="category.key" class="db-tree-item">
                            <div class="db-tree-row" :class="{ active: expandedCategory === category.key }">
                              <button class="db-tree-toggle" :aria-label="`${expandedCategory === category.key ? '收起' : '展开'}${category.label}`" :aria-expanded="expandedCategory === category.key" @click.stop="toggleCategory(category.key as 'table' | 'view' | 'procedure' | 'function')"><ChevronDown v-if="expandedCategory === category.key" :size="13" /><ChevronRight v-else :size="13" /></button>
                              <Table2 class="db-tree-object-icon" :size="14" />
                              <button class="db-tree-label" @click="toggleCategory(category.key as ObjectCategory)"><span>{{ category.label }}</span><small class="db-tree-count">{{ objectCounts[category.key as ObjectCategory] ?? '-' }}</small></button>
                            </div>
                            <div v-if="expandedCategory === category.key" class="db-tree-children db-object-items">
                              <button v-for="object in tables" :key="object.name" class="db-tree-object-row" :class="{ active: activeTable === object.name }" @click="selectTable(object.name)" @contextmenu.prevent="openTreeMenu($event, 'object', object.name)"><Table2 :size="13" /><span>{{ object.name }}</span></button>
                              <span v-if="!tables.length" class="db-tree-empty">暂无{{ category.label }}</span>
                            </div>
                          </div>
                          <div class="db-tree-item">
                            <div class="db-tree-row" :class="{ active: expandedQuery && tab === 'sql' }"><button class="db-tree-toggle" :aria-label="expandedQuery ? '收起查询' : '展开查询'" :aria-expanded="expandedQuery" @click.stop="toggleQuery"><ChevronDown v-if="expandedQuery" :size="13" /><ChevronRight v-else :size="13" /></button><Search class="db-tree-query-icon" :size="14" /><button class="db-tree-label" @click="toggleQuery"><span>查询</span><small class="db-tree-count">0</small></button></div>
                            <div v-if="expandedQuery" class="db-tree-children"><button class="db-tree-object-row" :class="{ active: tab === 'sql' }" @click="tab = 'sql'"><Search :size="13" /><span>SQL 编辑器</span></button></div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </template>
        </div>
        <div v-if="!assets.length && directories.length" class="db-empty">目录中暂无连接资产</div>
      </div>
    </aside>
    <div v-if="treeMenu" class="db-context-menu hex-menu" :style="{ left: `${treeMenu.x}px`, top: `${treeMenu.y}px` }" @click.stop>
      <button v-for="action in menuActions" :key="action.id" :class="{ 'has-submenu': action.children }" @mouseenter="menuSubmenu = action.id" @click="action.children ? undefined : runMenuAction(action.id)">{{ action.label }}<ChevronRight v-if="action.children" :size="14" /></button>
      <div v-if="menuSubmenu" class="db-context-submenu">
        <template v-for="action in menuActions" :key="action.id"><button v-for="child in action.id === menuSubmenu ? action.children : []" :key="child.id" @click="runMenuAction(child.id)">{{ child.label }}</button></template>
      </div>
    </div>

    <main class="db-main">
      <template v-if="!selected || !connected"><div class="db-center-empty"><Database :size="36" /><strong>{{ connecting ? '正在连接数据库' : '选择左侧连接资产' }}</strong></div></template>
      <template v-else-if="isRedis">
        <header class="db-main-head"><div><h2>{{ selected.name }}</h2><p>Redis · 键值数据</p></div><div class="db-actions"><el-button v-if="can('import_export')" @click="importInput?.click()"><Upload :size="15" />导入</el-button><el-dropdown v-if="can('import_export')" @command="exportFile"><el-button><Download :size="15" />导出</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="json">JSON</el-dropdown-item><el-dropdown-item command="csv">CSV</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></header>
        <div class="db-redis-layout"><div class="db-redis-list"><div class="db-inline"><el-input v-model="redisPattern" placeholder="匹配键名" @keyup.enter="loadRedis()" /><el-button title="搜索" @click="loadRedis()"><Search :size="16" /></el-button></div><button v-for="item in redisKeys" :key="item.key" class="db-redis-key" :class="{ active: redisDetail?.key === item.key }" @click="selectRedisKey(item.key)"><strong>{{ item.key }}</strong><small>{{ item.type }} · TTL {{ item.ttl }} · {{ item.size }} B</small></button></div>
          <div class="db-redis-detail"><template v-if="redisDetail"><div class="db-redis-title"><div><h3>{{ redisDetail.key }}</h3><p>{{ redisDetail.type }} · TTL {{ redisDetail.ttl }}</p></div><el-button v-if="can('redis_command')" type="danger" text @click="removeRedisKey">删除</el-button></div><el-input v-model="redisValueDraft" type="textarea" :rows="8" :disabled="!can('redis_command')" /><div class="db-redis-edit"><el-input-number v-model="redisTtl" :min="-1" /><el-button v-if="can('redis_command')" @click="saveRedisTtl">更新 TTL</el-button><el-button v-if="can('redis_command')" type="primary" @click="saveRedisValue">保存值</el-button></div></template><div v-else class="db-center-empty">选择键查看数据</div><div v-if="can('redis_command')" class="db-command"><el-input v-model="redisCommand" placeholder="Redis 命令" @keyup.enter="runRedis" /><el-button type="primary" @click="runRedis"><Play :size="15" /></el-button><pre v-if="redisResult">{{ redisResult }}</pre></div></div>
        </div>
      </template>
      <template v-else><header class="db-main-head"><div><h2>{{ selected.name }}</h2><p>{{ activeDatabase || '选择数据库' }} <span v-if="activeTable">/ {{ activeTable }}</span></p></div><div class="db-actions"><el-button title="刷新" @click="activeTable ? loadData() : loadObjects()"><RefreshCw :size="15" /></el-button><el-button v-if="can('import_export')" :disabled="!activeTable" @click="importInput?.click()"><Upload :size="15" />导入</el-button><el-dropdown v-if="can('import_export')" @command="exportFile"><el-button :disabled="!activeTable"><Download :size="15" />导出</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="csv">CSV</el-dropdown-item><el-dropdown-item command="sql">SQL</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></header>
        <nav class="db-tabs"><button v-for="item in [{ key: 'tables', label: '表列表' }, { key: 'structure', label: '表结构' }, { key: 'data', label: '表数据' }, { key: 'sql', label: 'SQL 编辑器' }, { key: 'transfer', label: '导入导出' }]" :key="item.key" :class="{ active: tab === item.key }" @click="tab = item.key as Tab">{{ item.label }}</button></nav>
        <section class="db-content">
          <template v-if="tab === 'tables'"><div class="db-object-toolbar"><button class="db-sort-button" @click="objectSortAsc = !objectSortAsc">名称 {{ objectSortAsc ? '↑' : '↓' }}</button><span>共 {{ visibleTables.length }} 个对象</span><div class="db-view-switch"><button title="列表视图" :class="{ active: tableView === 'list' }" @click="tableView = 'list'"><LayoutList :size="16" /></button><button title="表格视图" :class="{ active: tableView === 'table' }" @click="tableView = 'table'"><Table2 :size="16" /></button></div><el-input v-model="objectSearch" clearable placeholder="搜索对象"><template #prefix><Search :size="14" /></template></el-input></div><div v-if="tableView === 'list'" class="db-object-list"><button v-for="item in visibleTables" :key="item.name" class="db-object-item" :class="{ active: activeTable === item.name }" @click="selectTable(item.name)" @contextmenu.prevent="openTreeMenu($event, 'object', item.name)"><Table2 :size="20" /><strong>{{ item.name }}</strong><small>{{ item.type }} · {{ item.rows_count ?? '-' }} 行</small></button><div v-if="!visibleTables.length" class="db-empty">暂无对象</div></div><el-table v-else :data="visibleTables" height="100%" @row-click="(row: DatabaseTable) => selectTable(row.name)"><el-table-column prop="name" label="名称" min-width="220" /><el-table-column prop="type" label="类型" width="160" /><el-table-column prop="rows_count" label="行数" width="120" /><el-table-column prop="engine" label="引擎" width="140" /><el-table-column prop="update_time" label="更新时间" width="180" /><el-table-column prop="comment" label="备注" min-width="180" /></el-table></template>
          <template v-else-if="tab === 'structure'"><el-empty v-if="!activeTable" description="从左侧选择表" /><template v-else><div v-if="can('manage_schema')" class="db-data-tools db-schema-actions"><el-button size="small" @click="openSchema('add_column')">新增字段</el-button><el-button size="small" @click="openSchema('create_index')">新增索引</el-button></div><el-table :data="columns" height="42%"><el-table-column prop="name" label="字段" min-width="170" /><el-table-column prop="type" label="类型" min-width="150" /><el-table-column prop="nullable" label="可空" width="90" /><el-table-column prop="column_key" label="键" width="80" /><el-table-column prop="default" label="默认值" min-width="140" /><el-table-column v-if="can('manage_schema')" label="操作" width="100"><template #default="scope"><el-button text size="small" type="danger" @click="openSchema('drop_column', { name: scope.row.name })">删除</el-button></template></el-table-column></el-table><div class="db-index-list"><strong>索引</strong><el-table :data="indexes" height="100%"><el-table-column prop="name" label="名称" min-width="160" /><el-table-column label="字段" min-width="200"><template #default="scope">{{ scope.row.columns.join(', ') }}</template></el-table-column><el-table-column prop="unique" label="唯一" width="80" /><el-table-column v-if="can('manage_schema')" label="操作" width="100"><template #default="scope"><el-button text size="small" type="danger" @click="openSchema('drop_index', scope.row)">删除</el-button></template></el-table-column></el-table></div></template></template>
          <template v-else-if="tab === 'data'"><el-empty v-if="!activeTable" description="从左侧选择表" /><template v-else>
             <div class="db-data-tools"><el-select v-model="selectedFields" multiple collapse-tags placeholder="字段"><el-option v-for="field in allDataColumns" :key="field" :label="field" :value="field" /></el-select><el-select v-model="whereField" clearable placeholder="筛选字段"><el-option v-for="field in allDataColumns" :key="field" :label="field" :value="field" /></el-select><el-input v-model="whereValue" clearable placeholder="筛选值" @keyup.enter="loadData" /><el-select v-model="sort" clearable placeholder="排序字段"><el-option v-for="field in allDataColumns" :key="field" :label="field" :value="field" /></el-select><el-select v-model="direction"><el-option label="升序" value="asc" /><el-option label="降序" value="desc" /></el-select><el-button @click="loadData">应用</el-button><el-button v-if="can('modify_data')" type="primary" @click="openRow('insert')"><Plus :size="15" />新增行</el-button><el-button v-if="can('modify_data') && !transaction" @click="transaction = true">事务暂存</el-button><el-button v-if="transaction" type="success" :disabled="!stagedChanges.length" @click="commitRows">提交 ({{ stagedChanges.length }})</el-button><el-button v-if="transaction" @click="rollbackRows">回滚</el-button></div>
            <el-table v-loading="loading" :data="rows" border stripe height="100%"><el-table-column v-for="field in tableDataColumns" :key="field" :prop="field" :label="field" min-width="150" show-overflow-tooltip /><el-table-column v-if="can('modify_data')" label="操作" width="130" fixed="right"><template #default="scope"><el-button text size="small" @click="openRow('update', scope.row)">编辑</el-button><el-button text size="small" type="danger" @click="removeRow(scope.row)"><Trash2 :size="14" /></el-button></template></el-table-column></el-table><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" layout="total, sizes, prev, pager, next" @current-change="loadData" @size-change="loadData" />
          </template></template>
          <template v-else-if="tab === 'sql'"><div class="db-sql-toolbar"><el-select :model-value="activeDatabase" placeholder="数据库" @change="selectDatabase"><el-option v-for="name in databases" :key="name" :label="name" :value="name" /></el-select><el-select v-if="schemas.length" :model-value="schema" placeholder="Schema" @change="selectSchema"><el-option v-for="name in schemas" :key="name" :label="name" :value="name" /></el-select></div><div class="db-sql-toolbar"><el-button type="primary" :loading="sqlRunning" :disabled="!can('execute_sql')" @click="runSql"><Play :size="15" />执行</el-button><el-button v-if="sqlRunning" @click="stopSql">取消等待</el-button><el-button @click="formatSql">格式化</el-button><el-button @click="compressSql">压缩</el-button><el-button :disabled="sqlRunning || !can('execute_sql')" @click="explainSql">执行计划</el-button><span>{{ sqlMessage }}</span></div><el-input v-model="sql" type="textarea" :rows="10" placeholder="输入 SQL" /><el-table v-if="sqlRows.length" :data="sqlRows" border height="100%"><el-table-column v-for="field in Object.keys(sqlRows[0])" :key="field" :prop="field" :label="field" min-width="150" /></el-table></template>
          <template v-else><el-empty v-if="!can('import_export')" description="当前账号没有导入导出权限" /><el-empty v-else-if="!activeTable" description="从左侧选择表" /><div v-else class="db-transfer-panel"><h3>{{ activeTable }}</h3><div class="db-transfer-actions"><el-button type="primary" @click="importInput?.click()"><Upload :size="15" />导入</el-button><el-button @click="exportFile('csv')"><Download :size="15" />CSV</el-button><el-button @click="exportFile('sql')"><Download :size="15" />SQL</el-button></div></div></template>
        </section>
      </template>
    </main>

    <input ref="importInput" class="db-hidden" type="file" accept=".csv,.sql,.json" @change="onImport" />
    <input ref="configInput" class="db-hidden" type="file" accept=".json" @change="onConnectionImport" />
    <input ref="databaseInput" class="db-hidden" type="file" accept=".json" @change="onDatabaseImport" />
    <el-dialog :close-on-click-modal="false" v-model="directoryDialog" :title="editingDirectory ? '重命名目录' : '新建目录'" width="min(420px, 94vw)"><el-input v-model="directoryName" maxlength="160" placeholder="目录名称" @keyup.enter="saveDirectory" /><template #footer><el-button @click="directoryDialog = false">取消</el-button><el-button type="primary" @click="saveDirectory">保存</el-button></template></el-dialog>
    <el-dialog :close-on-click-modal="false" v-model="moveDialog" title="移动到目录" width="min(420px, 94vw)"><el-select v-model="moveTarget" placeholder="选择目标目录" style="width:100%"><el-option label="根目录" :value="null" /><el-option v-for="folder in directories" :key="folder.id" :label="folder.name" :value="folder.id" /></el-select><template #footer><el-button @click="moveDialog = false">取消</el-button><el-button type="primary" @click="saveMove">移动</el-button></template></el-dialog>
    <el-dialog :close-on-click-modal="false" v-model="databaseDialog" :title="({ create: '新建数据库', delete: '删除数据库', clear: '清空数据库', import: '导入数据库' } as Record<string, string>)[databaseAction]" width="min(440px, 94vw)"><el-input v-model="databaseTarget" :placeholder="selected?.dbType === 'sqlite' ? '受限目录中的 .db 文件名' : selected?.dbType === 'redis' ? 'DB 编号 0-255' : '数据库名称'" /><template #footer><el-button @click="databaseDialog = false">取消</el-button><el-button type="primary" @click="saveDatabaseAction">确认</el-button></template></el-dialog>
    <el-dialog v-model="dialog" :close-on-click-modal="false" :title="editing ? '编辑连接' : '新建连接'" width="min(520px, 94vw)"><el-form label-position="top"><el-form-item label="数据库类型"><el-select v-model="form.dbType" :disabled="!!editing" @change="form = emptyForm(form.dbType)"><el-option v-for="kind in types" :key="kind.key" :label="kind.label" :value="kind.key" /></el-select></el-form-item><el-form-item label="名称"><el-input v-model="form.name" /></el-form-item><template v-if="form.dbType === 'sqlite'"><el-form-item label="SQLite 文件"><el-select v-model="form.options.file" placeholder="选择服务器文件"><el-option v-for="file in files" :key="file" :label="file" :value="file" /></el-select></el-form-item></template><template v-else><el-form-item label="主机"><el-input v-model="form.host" /></el-form-item><el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item><el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item><el-form-item label="密码"><el-input v-model="form.password" type="password" show-password :placeholder="editing ? '留空保持原密码' : ''" /></el-form-item><el-form-item v-if="form.dbType !== 'redis'" label="默认数据库"><el-input v-model="form.databaseName" /></el-form-item><el-form-item v-for="field in activeType?.fields.filter(item => !['file'].includes(item))" :key="field" :label="({ db: 'Redis DB 编号', https: 'HTTPS', service: 'Oracle Service Name', sid: 'Oracle SID', schema: '默认 Schema', instance: '实例名', ssl: 'SSL' } as Record<string, string>)[field] || field"><el-switch v-if="['ssl', 'https'].includes(field)" v-model="form.options[field]" /><el-input-number v-else-if="field === 'db'" v-model="form.options[field]" :min="0" :max="255" /><el-input v-else v-model="form.options[field]" /></el-form-item></template><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item></el-form><template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="saveAsset">保存</el-button></template></el-dialog>
    <el-dialog v-model="rowDialog" :close-on-click-modal="false" :title="editMode === 'insert' ? '新增数据行' : '编辑数据行'" width="min(520px, 94vw)"><el-form v-if="editingRow" label-position="top"><el-form-item v-for="field in allDataColumns" :key="field" :label="field"><el-input v-model="editingRow[field]" /></el-form-item></el-form><template #footer><el-button @click="rowDialog = false">取消</el-button><el-button type="primary" @click="saveRow">保存</el-button></template></el-dialog>
    <el-dialog v-model="schemaDialog" :close-on-click-modal="false" title="表结构操作" width="min(520px, 94vw)"><el-form label-position="top"><el-form-item v-if="['drop_column', 'drop_index'].includes(schemaAction)" label="名称"><el-input v-model="schemaForm.name" disabled /></el-form-item><template v-if="schemaAction === 'add_column'"><el-form-item label="字段名"><el-input v-model="schemaForm.name" /></el-form-item><el-form-item label="字段类型"><el-input v-model="schemaForm.columnType" placeholder="例如 VARCHAR(255)" /></el-form-item></template><template v-else-if="schemaAction === 'create_index'"><el-form-item label="索引名"><el-input v-model="schemaForm.name" /></el-form-item><el-form-item label="字段"><el-select v-model="schemaForm.columns" multiple><el-option v-for="column in columns" :key="column.name" :label="column.name" :value="column.name" /></el-select></el-form-item><el-form-item label="唯一索引"><el-switch v-model="schemaForm.unique" /></el-form-item></template></el-form><template #footer><el-button @click="schemaDialog = false">取消</el-button><el-button type="primary" @click="saveSchema">执行</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.db-workspace{height:100%;min-height:0;display:grid;grid-template-columns:minmax(240px,280px) minmax(0,1fr);border:1px solid var(--border-color,#dce2e9);background:var(--panel-bg,#fff);overflow:hidden}.db-sidebar{min-width:0;border-right:1px solid var(--border-color,#dce2e9);display:flex;flex-direction:column;padding:14px;gap:12px}.db-sidebar-head,.db-main-head,.db-actions,.db-inline,.db-data-tools,.db-sql-toolbar{display:flex;align-items:center;gap:8px}.db-sidebar-head,.db-main-head{justify-content:space-between}.db-sidebar-head strong{font-size:16px}.db-actions .el-button+.el-button{margin-left:0}.db-asset-scroll{min-height:0;overflow:auto;flex:1}.db-asset-line{display:flex;align-items:center;border-radius:5px}.db-asset-line.active,.db-tree-node.active,.db-redis-key.active{background:var(--el-color-primary-light-9,#edf4ff)}.db-asset-main{display:flex;align-items:center;gap:8px;min-width:0;flex:1;text-align:left;border:0;background:none;padding:8px;cursor:pointer;color:inherit}.db-asset-main span{min-width:0}.db-asset-main strong,.db-asset-main small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.db-asset-main small{color:var(--el-text-color-secondary,#778);font-size:11px}.db-type-option{display:flex;align-items:center;gap:8px;width:100%;padding:7px;border:0;background:none;text-align:left;cursor:pointer;color:inherit}.db-type-option:hover{background:var(--el-fill-color-light,#eee)}.db-tree{padding-left:22px}.db-tree-branch{padding-left:15px;border-left:1px solid var(--border-color,#ddd)}.db-tree-node,.db-tree-category{display:block;width:100%;text-align:left;border:0;background:none;padding:6px 8px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:inherit}.db-tree-category{font-size:12px;color:var(--el-text-color-secondary,#778)}.db-main{min-width:0;min-height:0;overflow:hidden;display:flex;flex-direction:column}.db-main-head{flex:none;padding:14px 18px;border-bottom:1px solid var(--border-color,#ddd);min-height:64px}.db-main-head h2{margin:0;font-size:16px}.db-main-head p{margin:3px 0 0;font-size:12px;color:var(--el-text-color-secondary,#778)}.db-tabs{flex:none;display:flex;border-bottom:1px solid var(--border-color,#ddd);overflow:auto}.db-tabs button{border:0;border-bottom:2px solid transparent;background:none;color:inherit;padding:10px 16px;white-space:nowrap;cursor:pointer}.db-tabs button.active{border-bottom-color:var(--el-color-primary,#409eff);color:var(--el-color-primary,#409eff)}.db-content{flex:1;min-height:0;overflow:auto;padding:12px 16px;display:flex;flex-direction:column;gap:10px}.db-content>.el-table{flex:1}.db-data-tools .el-select{width:145px}.db-sql-toolbar{justify-content:flex-start}.db-sql-toolbar span{font-size:12px;color:var(--el-text-color-secondary,#778)}.db-center-empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--el-text-color-secondary,#778)}.db-redis-layout{display:grid;grid-template-columns:260px minmax(0,1fr);flex:1;min-height:0}.db-redis-list{border-right:1px solid var(--border-color,#ddd);padding:12px;overflow:auto}.db-redis-key{width:100%;display:block;text-align:left;padding:8px;border:0;background:none;color:inherit;cursor:pointer}.db-redis-key strong,.db-redis-key small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.db-redis-key small{font-size:11px;color:var(--el-text-color-secondary,#778)}.db-redis-detail{min-width:0;overflow:auto;padding:18px;display:flex;flex-direction:column}.db-redis-detail h3{margin:0}.db-redis-detail pre,.db-command pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--el-fill-color-light,#f3f4f6);padding:10px;border-radius:4px}.db-command{margin-top:auto;padding-top:18px;display:flex;gap:8px;flex-wrap:wrap}.db-command .el-input{flex:1}.db-command pre{width:100%}.db-hidden{display:none}.db-empty{padding:20px;text-align:center;color:var(--el-text-color-secondary,#778)}@media(max-width:720px){.db-workspace{display:flex;flex-direction:column;min-height:0}.db-sidebar{flex:0 0 250px;height:auto;border-right:0;border-bottom:1px solid var(--border-color,#ddd)}.db-main{flex:1;min-height:0}.db-main-head{flex-wrap:wrap}.db-redis-layout{grid-template-columns:38% minmax(0,1fr)}.db-data-tools{flex-wrap:wrap}}
.db-data-tools,.db-sql-toolbar,.db-redis-edit,.db-redis-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
.db-data-tools .el-input{width:140px}
.db-redis-title{justify-content:space-between}
.db-redis-title h3{overflow-wrap:anywhere}
.db-redis-edit{margin-top:12px}
.db-content,.db-main,.db-redis-detail{min-width:0}
.db-schema-actions{padding:8px 0}.db-index-list{height:45%;min-height:120px;margin-top:8px;display:flex;flex-direction:column;gap:6px}.db-index-list .el-table{min-height:0}.db-context-menu{position:fixed;z-index:3000;display:flex;flex-direction:column;min-width:150px;padding:4px;background:var(--el-bg-color,#fff);border:1px solid var(--el-border-color,#dcdfe6);box-shadow:var(--el-box-shadow-light,0 2px 12px rgba(0,0,0,.1));border-radius:4px}.db-context-menu button{padding:7px 12px;text-align:left;border:0;background:none;color:inherit;cursor:pointer}.db-context-menu button:hover{background:var(--el-fill-color-light,#f5f7fa)}
.db-transfer-panel h3{margin:0 0 16px;font-size:16px;overflow-wrap:anywhere}.db-transfer-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.db-transfer-actions .el-button+.el-button{margin-left:0}
@media(max-width:720px){.db-main-head,.db-content{padding-left:10px;padding-right:10px}.db-redis-edit .el-input-number{width:110px}}
.db-sidebar{padding:10px 8px;gap:8px;background:var(--el-fill-color-extra-light,#f7f9fb)}
.db-sidebar-head{padding:2px 5px}.db-sidebar-head strong{font-size:14px}
.db-asset-scroll{padding:4px 0;min-height:120px}
.db-catalog-root,.db-catalog-entry{display:flex;align-items:center;gap:6px;min-height:34px;min-width:0;padding:0 8px;color:var(--el-text-color-primary,#293344);border-radius:3px}
.db-catalog-root{cursor:pointer;font-size:12px;font-weight:600}
.db-catalog-entry:hover,.db-catalog-root:hover{background:var(--el-fill-color-light,#e9eff4)}
.db-catalog-entry>svg,.db-catalog-root>svg{flex:none;color:#4e8b7b}
.db-catalog-label{display:flex;align-items:center;gap:5px;min-width:0;flex:1;padding:3px 0;border:0;background:none;color:inherit;text-align:left;cursor:pointer;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db-catalog-label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db-catalog-label small{font-size:10px;color:var(--el-text-color-secondary,#64748b);white-space:nowrap}
.db-catalog-label.active{color:var(--el-color-primary,#287f69);font-weight:600}
.db-tree-toggle{display:grid;place-items:center;width:16px;height:22px;flex:none;border:0;background:none;color:inherit;cursor:pointer}
.db-tree-node,.db-tree-category{font-size:12px;padding:5px 6px;min-height:27px;text-align:left}
.hex-menu{min-width:188px;border-radius:6px;background:color-mix(in srgb,var(--el-bg-color,#fff) 78%,transparent);backdrop-filter:blur(24px);box-shadow:0 8px 30px rgba(20,30,35,.18);padding:5px}
.hex-menu button{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:29px;font-size:12px;border-radius:3px}
.hex-menu button:hover{background:var(--el-color-primary-light-9,#dcefe9)}
.db-context-submenu{position:absolute;left:calc(100% - 2px);top:0;min-width:170px;padding:5px;border:1px solid var(--el-border-color,#dcdfe6);border-radius:6px;background:var(--el-bg-color,#fff);box-shadow:0 8px 30px rgba(20,30,35,.18)}
.db-object-toolbar{display:flex;align-items:center;gap:12px;min-height:36px;flex-wrap:wrap;font-size:12px;color:var(--el-text-color-secondary,#64748b)}
.db-object-toolbar>.el-input{margin-left:auto;width:180px}.db-sort-button{border:0;background:none;color:var(--el-text-color-primary,#293344);cursor:pointer;font-size:12px}
.db-view-switch{display:flex;border:1px solid var(--el-border-color,#dcdfe6);border-radius:3px;overflow:hidden}
.db-view-switch button{display:grid;place-items:center;width:30px;height:28px;border:0;background:none;color:inherit;cursor:pointer}
.db-view-switch button.active{background:var(--el-color-primary-light-9,#dcefe9);color:var(--el-color-primary,#287f69)}
.db-object-list{flex:1;min-height:0;overflow:auto;display:grid;align-content:start;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:3px}
.db-object-item{display:flex;align-items:center;gap:9px;min-width:0;height:42px;padding:4px 8px;border:1px solid transparent;border-radius:3px;background:none;color:inherit;text-align:left;cursor:pointer}
.db-object-item:hover,.db-object-item.active{background:var(--el-fill-color-light,#edf2f5);border-color:var(--el-border-color,#dce2e9)}
.db-object-item>svg{flex:none;color:#427b9f}.db-object-item strong{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:500}.db-object-item small{margin-left:auto;white-space:nowrap;font-size:10px;color:var(--el-text-color-secondary,#64748b)}
@media(max-width:720px){.db-sidebar{height:250px}.db-object-toolbar>.el-input{width:140px}.db-object-list{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}.db-object-item small{display:none}.db-context-submenu{left:auto;right:calc(100% - 2px)}}
.db-workspace{grid-template-columns:284px minmax(0,1fr)}
.db-sidebar{padding:8px 7px;gap:6px;background:var(--el-fill-color-extra-light,#f7f9fb)}
.db-sidebar-head{min-height:30px;padding:0 3px;gap:5px}
.db-sidebar-head strong{font-size:13px;white-space:nowrap}
.db-sidebar-head .db-actions{gap:1px;min-width:0}
.db-sidebar-head .el-button{width:26px;height:26px;padding:0}
.db-sidebar-head .el-button.active{color:var(--el-color-primary,#287f69);background:var(--el-color-primary-light-9,#dcefe9)}
.db-sidebar-search{width:84px}
.db-sidebar-search .el-input__wrapper{padding:0 7px}
.db-asset-scroll{padding:2px 0;min-height:120px}
.db-catalog-entry{display:block;min-height:32px;padding-top:0;padding-bottom:0}
.db-catalog-row{display:flex;align-items:center;gap:4px;min-width:0;min-height:32px;border-radius:3px;padding:0 3px}
.db-catalog-row:hover,.db-catalog-row.active{background:var(--el-fill-color-light,#e9eff4)}
.db-catalog-row.active{color:var(--el-color-primary,#287f69)}
.db-catalog-label{justify-content:flex-start;font-size:12px;line-height:15px}
.db-catalog-label small{font-size:10px}
.db-tree-toggle{width:16px;height:22px;padding:0}
.db-folder-icon{color:#4e8b7b;flex:none}
.db-asset-icon{flex:none;color:#368b66}
.db-asset-icon.redis{color:#d84a4a}
.db-asset-more{display:grid;place-items:center;flex:none;width:22px;height:24px;padding:0;border:0;border-radius:3px;background:none;color:var(--el-text-color-secondary,#64748b);cursor:pointer}
.db-asset-more:hover{background:var(--el-fill-color,#e5e7eb);color:var(--el-text-color-primary,#293344)}
.db-asset-children{margin:0 0 3px 10px;padding:2px 0 2px 6px;border-left:1px solid var(--el-border-color,#dce2e9)}
.db-asset-children .db-tree-node,.db-asset-children .db-tree-category{min-height:26px;padding:4px 6px;font-size:11px}
.db-asset-children .db-tree-branch{padding-left:8px}
.db-asset-children .db-tree-node.active,.db-asset-children .db-tree-category.active{background:var(--el-color-primary-light-9,#edf4ff);border-radius:3px}
@media(max-width:720px){.db-workspace{grid-template-columns:1fr}.db-sidebar-head .db-sidebar-search{width:130px}.db-asset-children{max-height:150px;overflow:auto}}
.db-tree-level,.db-tree-children{display:flex;flex-direction:column;min-width:0}
.db-tree-item{min-width:0}
.db-tree-row{display:flex;align-items:center;gap:4px;min-width:0;min-height:28px;padding:0 3px;border-radius:3px}
.db-tree-row:hover,.db-tree-row.active{background:var(--el-fill-color-light,#e9eff4)}
.db-tree-row.active{color:var(--el-color-primary,#287f69)}
.db-tree-children{margin-left:5px;padding-left:7px;border-left:1px solid var(--el-border-color,#dce2e9)}
.db-object-level{margin-left:5px}
.db-object-level-flat{margin-left:0;padding-left:0;border-left:0}
.db-tree-label{display:flex;align-items:center;justify-content:flex-start;gap:6px;min-width:0;flex:1;border:0;background:none;padding:3px 0;color:inherit;text-align:left;cursor:pointer;font-size:12px;line-height:17px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db-tree-label>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db-tree-count{flex:none;margin-left:auto;min-width:22px;padding:1px 4px;border:1px solid var(--el-border-color,#dce2e9);border-radius:3px;background:var(--el-fill-color-lighter,#f7f9fb);color:var(--el-text-color-secondary,#64748b);font-size:10px;font-weight:500;line-height:16px;text-align:center}
.db-tree-database-icon{flex:none;color:#65a84b}.db-tree-schema-icon{flex:none;color:#70b34f}.db-tree-object-icon{flex:none;color:#4da7a0}.db-tree-query-icon{flex:none;color:#5798ed}
.db-redis-db-row{padding-left:6px}.db-redis-db-row .db-tree-label{padding-right:6px}
.db-tree-object-row{display:flex;align-items:center;justify-content:flex-start;gap:6px;min-width:0;width:100%;min-height:28px;padding:3px 5px 3px 7px;border:0;border-radius:3px;background:none;color:inherit;text-align:left;cursor:pointer;font-size:12px}
.db-tree-object-row:hover,.db-tree-object-row.active{background:var(--el-color-primary-light-9,#edf4ff)}
.db-tree-object-row svg{flex:none;color:#8aa1a5}.db-tree-object-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db-tree-empty{padding:4px 7px;color:var(--el-text-color-placeholder,#a8abb2);font-size:11px;text-align:left}
/* The shared button reset centers native buttons. Tree controls must keep their label at the branch start. */
.db-sidebar .db-catalog-label,
.db-sidebar .db-tree-label,
.db-sidebar .db-tree-node,
.db-sidebar .db-tree-category,
.db-sidebar .db-tree-object-row{
  display:flex !important;
  align-items:center !important;
  justify-content:flex-start !important;
  width:100%;
  min-height:27px !important;
  margin:0;
  padding:4px 6px !important;
  border:0 !important;
  border-radius:3px !important;
  background:none !important;
  box-shadow:none !important;
  color:inherit !important;
  font-size:12px;
  font-weight:500 !important;
  text-align:left !important;
}
.db-sidebar .db-catalog-label{min-height:24px !important;padding:3px 0 !important}
.db-sidebar .db-catalog-label.active{font-weight:600 !important}
.db-sidebar .db-tree-label{flex:1;min-width:0;line-height:17px}
.db-sidebar .db-tree-node,.db-sidebar .db-tree-category{font-size:11px}
.db-sidebar .db-tree-object-row{min-height:28px !important;padding:3px 5px 3px 7px !important}
.db-sidebar .db-tree-node.active,
.db-sidebar .db-tree-category.active,
.db-sidebar .db-tree-object-row:hover,
.db-sidebar .db-tree-object-row.active{background:var(--el-color-primary-light-9,#edf4ff) !important}
.db-sidebar .db-tree-toggle,
.db-sidebar .db-asset-more{
  display:grid !important;
  place-items:center !important;
  width:16px;
  min-width:16px;
  height:22px;
  min-height:22px !important;
  padding:0 !important;
  border:0 !important;
  border-radius:3px !important;
  background:none !important;
  box-shadow:none !important;
  color:inherit !important;
}
.db-sidebar .db-asset-more{width:22px;min-width:22px;height:24px;color:var(--el-text-color-secondary,#64748b) !important}
.db-sidebar .db-tree-toggle:hover,
.db-sidebar .db-asset-more:hover{background:var(--el-fill-color,#e5e7eb) !important}
.db-sidebar .db-asset-more:hover{color:var(--el-text-color-primary,#293344) !important}
.db-workspace{width:100%;align-self:stretch;min-height:0}
.db-sidebar{min-height:0;overflow:hidden}
.db-asset-scroll{min-height:0;overflow-x:hidden;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--el-border-color-darker,#b8c0c8) transparent}
@media(max-width:720px){.db-sidebar{flex:0 0 250px}.db-asset-children{max-height:none;overflow:visible}}
</style>
