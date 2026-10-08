import { apiDelete, apiGet, apiPost, apiPostForm, apiPut } from '../../../api';

export interface DatabaseAsset { id: number; name: string; directoryId: number | null; dbType: string; host: string; port: number; username: string; databaseName: string; remark: string; options: Record<string, unknown>; }
export interface DatabaseAssetPayload { name: string; directoryId?: number | null; dbType: string; host: string; port: number; username: string; password?: string; databaseName: string; remark: string; options: Record<string, unknown>; applicationCredentialId?: number | null; }
export interface AssetDirectory { id: number; name: string; parentId: number | null; }
export interface ConnectionManifest { version: number; directories: string[][]; assets: Array<Record<string, unknown>>; }
export interface DatabaseType { key: string; label: string; defaultPort: number; fields: string[]; capabilities: string[]; }
export interface DatabaseTable { name: string; type: string; signature?: string; capabilities?: string[]; rows_count: number | null; data_length?: number | null; index_length?: number | null; auto_increment?: number | null; engine?: string | null; charset?: string | null; update_time?: string | null; create_time?: string | null; comment: string; }
export interface SavedDatabaseQuery { id: number; assetId: number; database: string; schema: string; name: string; sql: string; pinned: boolean; createdAt: string; updatedAt: string; }
export interface DatabaseAccount { name: string; host?: string; roles: string[]; permissions: string[]; availableRoles?: { name: string; host: string }[]; current?: boolean; builtIn?: boolean; protected?: boolean; capabilities?: { passwordReset: boolean; delete: boolean; grants: string[]; roles?: boolean }; }
export interface DatabaseColumn { name: string; type: string; nullable: string; column_key: string; comment: string; default?: unknown; }
export interface DatabaseIndex { name: string; columns: string[]; unique: boolean; definition?: string; }
export interface DatabaseDataResult { rows: Record<string, unknown>[]; total: number; page: number; pageSize: number; hasNext: boolean; }
export interface DatabaseTransferTask { id: string; assetId: number | null; assetName: string; direction: 'import' | 'export'; scope: string; format: string; database: string; schema: string; objectName: string; status: string; stage: string; progress: number; processedRows: number; processedBytes: number; totalRows: number | null; totalBytes: number | null; preview: Record<string, unknown>; checkpoints?: { completedTables?: string[]; currentTable?: string; ddlMayBeCommitted?: boolean }; sourceName: string; error: string; conflictPolicy: string; cancelRequested: boolean; createdAt: string; startedAt: string | null; finishedAt: string | null; expiresAt: string; canDownload: boolean; chunkBytes?: number; }

const base = '/api/database-management';
function query(params: Record<string, unknown>) { const search = new URLSearchParams(); Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== null && value !== '') search.set(key, String(value)); }); const text = search.toString(); return text ? `?${text}` : ''; }
export const listDatabaseTypes = () => apiGet<{ types: DatabaseType[] }>(`${base}/types/`);
export const listSQLiteFiles = () => apiGet<{ files: string[] }>(`${base}/sqlite-files/`);
export const listDatabaseAssets = (keyword = '') => apiGet<DatabaseAsset[]>(`${base}/assets/${query({ keyword })}`);
export const listAssetDirectories = () => apiGet<AssetDirectory[]>(`${base}/directories/`);
export const createAssetDirectory = (name: string, parentId: number | null) => apiPost<AssetDirectory>(`${base}/directories/`, { name, parentId });
export const updateAssetDirectory = (id: number, payload: { name?: string; parentId?: number | null }) => apiPut<AssetDirectory>(`${base}/directories/${id}/`, payload);
export const deleteAssetDirectory = (id: number) => apiDelete<{ deleted: boolean }>(`${base}/directories/${id}/`);
export const copyAssetDirectory = (id: number, parentId: number | null) => apiPost<AssetDirectory>(`${base}/directories/${id}/copy/`, { parentId });
export const copyDatabaseAsset = (id: number) => apiPost<DatabaseAsset>(`${base}/assets/${id}/copy/`, {});
export const moveDatabaseAsset = (id: number, directoryId: number | null) => apiPost<DatabaseAsset>(`${base}/assets/${id}/move/`, { directoryId });
export const connectionManifestUrl = (directoryId?: number | null, assetId?: number | null) => `${base}/connections/${query({ directoryId, assetId })}`;
export const importConnectionManifest = (manifest: ConnectionManifest, directoryId?: number | null) => apiPost<{ imported: number }>(connectionManifestUrl(directoryId), manifest);
export const databaseAdmin = (id: number, action: string, name: string, snapshot?: unknown) => apiPost<Record<string, unknown>>(`${base}/assets/${id}/database/`, { action, name, snapshot });
export const databaseExportUrl = (id: number, name: string) => `${base}/assets/${id}/database/${query({ name })}`;
export const createDatabaseAsset = (payload: DatabaseAssetPayload) => apiPost<DatabaseAsset>(`${base}/assets/`, payload);
export const updateDatabaseAsset = (id: number, payload: Partial<DatabaseAssetPayload>) => apiPut<DatabaseAsset>(`${base}/assets/${id}/`, payload);
export const deleteDatabaseAsset = (id: number) => apiDelete<{ deleted: boolean }>(`${base}/assets/${id}/`);
export const testDatabaseAsset = (id: number) => apiPost<{ ok: boolean; message: string }>(`${base}/assets/${id}/test/`, {});
export const getDatabaseTree = (id: number, database = '') => apiGet<{ databases: string[]; schemas: string[]; kind: string }>(`${base}/assets/${id}/tree/${query({ database })}`);
export const listDatabaseObjects = (id: number, database: string, schema?: string, type?: string) => apiGet<{ objects: DatabaseTable[] }>(`${base}/assets/${id}/objects/${query({ database, schema, type })}`);
export const getDatabaseDdl = (id: number, database: string, table: string, schema?: string, objectType = 'table', signature = '') => apiGet<{ ddl: string }>(`${base}/assets/${id}/ddl/${query({ database, table, schema, objectType, signature })}`);
export const runDatabaseObjectAction = (id: number, data: Record<string, unknown>) => apiPost<{ ok: boolean }>(`${base}/assets/${id}/objects/action/`, data);
export const listSavedDatabaseQueries = (assetId: number, database: string) => apiGet<SavedDatabaseQuery[]>(`${base}/queries/${query({ assetId, database })}`);
export const createSavedDatabaseQuery = (data: Omit<SavedDatabaseQuery, 'id' | 'createdAt' | 'updatedAt'> & { imported?: boolean }) => apiPost<SavedDatabaseQuery>(`${base}/queries/`, data);
export const updateSavedDatabaseQuery = (id: number, data: Partial<SavedDatabaseQuery>) => apiPut<SavedDatabaseQuery>(`${base}/queries/${id}/`, data);
export const deleteSavedDatabaseQuery = (id: number) => apiDelete<{ deleted: boolean }>(`${base}/queries/${id}/`);
export const savedDatabaseQueryExportUrl = (id: number) => `${base}/queries/${id}/export/`;
export const listDatabaseAccounts = (id: number, database: string, schema?: string) => apiGet<DatabaseAccount[]>(`${base}/assets/${id}/accounts/${query({ database, schema })}`);
export const manageDatabaseAccount = (id: number, data: Record<string, unknown>, method: 'POST' | 'PUT' | 'DELETE' = 'POST') => method === 'DELETE' ? apiDelete<{ ok: boolean }>(`${base}/assets/${id}/accounts/`, { body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }) : method === 'PUT' ? apiPut<{ ok: boolean }>(`${base}/assets/${id}/accounts/`, data) : apiPost<{ ok: boolean }>(`${base}/assets/${id}/accounts/`, data);
export const getDatabaseColumns = (id: number, database: string, table: string, schema?: string) => apiGet<{ columns: DatabaseColumn[] }>(`${base}/assets/${id}/columns/${query({ database, table, schema })}`);
export const getDatabaseIndexes = (id: number, database: string, table: string, schema?: string) => apiGet<{ indexes: DatabaseIndex[] }>(`${base}/assets/${id}/indexes/${query({ database, table, schema })}`);
export const modifyDatabaseSchema = (id: number, data: Record<string, unknown>) => apiPost<{ ok: boolean }>(`${base}/assets/${id}/schema/`, data);
export const getDatabaseTableData = (id: number, params: Record<string, unknown>) => apiGet<DatabaseDataResult>(`${base}/assets/${id}/data/${query(params)}`);
export const executeDatabaseSql = (id: number, sql: string, database: string, signal?: AbortSignal) => apiPost<{ rows: Record<string, unknown>[]; affected: number; columns: string[]; elapsedMs: number }>(`${base}/assets/${id}/sql/`, { sql, database }, { signal });
export const runRedisCommand = (id: number, command: string[], db?: number) => apiPost<{ result: unknown }>(`${base}/assets/${id}/redis/`, { command, db });
export const updateRedisKey = (id: number, payload: Record<string, unknown>) => apiPost<{ result: unknown }>(`${base}/assets/${id}/redis/`, payload);
export const deleteRedisKey = (id: number, key: string, db?: number) => apiDelete<{ deleted: number }>(`${base}/assets/${id}/redis/`, { body: JSON.stringify({ key, db }), headers: { 'Content-Type': 'application/json' } });
export const getRedisKeys = (id: number, pattern = '*', db?: number) => apiGet<{ keys: { key: string; type: string; ttl: number; size: number }[]; counts: number[] }>(`${base}/assets/${id}/redis/${query({ pattern, db })}`);
export const getRedisValue = (id: number, key: string, db?: number) => apiGet<{ key: string; type: string; ttl: number; value: unknown }>(`${base}/assets/${id}/redis/${query({ key, db })}`);
export const modifyDatabaseRow = (id: number, data: Record<string, unknown>) => apiPost<{ affected: number }>(`${base}/assets/${id}/rows/`, data);
export const commitDatabaseRows = (id: number, data: Record<string, unknown>) => apiPost<{ affected: number }>(`${base}/assets/${id}/transaction/`, { action: 'commit', ...data });
export const importDatabaseFile = (id: number, body: FormData) => apiPostForm<{ imported: number }>(`${base}/assets/${id}/import/`, body);
export const exportDatabaseUrl = (id: number, params: Record<string, unknown>) => `${base}/assets/${id}/export/${query(params)}`;
const transfers = `${base}/transfers/`;
export const listDatabaseTransferTasks = () => apiGet<DatabaseTransferTask[]>(transfers);
export const createDatabaseTransfer = (data: Record<string, unknown>) => apiPost<DatabaseTransferTask>(transfers, data);
export const beginDatabaseTransferUpload = (data: Record<string, unknown>) => apiPost<DatabaseTransferTask>(`${transfers}uploads/`, data);
export const uploadDatabaseTransferChunk = (id: string, index: number, chunk: Blob) => apiRequestTransfer<void>(`${transfers}${id}/chunks/${index}/`, 'PUT', chunk);
export const completeDatabaseTransferUpload = (id: string, chunks: number, sha256: string) => apiPost<DatabaseTransferTask>(`${transfers}${id}/complete/`, { chunks, sha256 });
export const confirmDatabaseTransfer = (id: string, conflictPolicy: string, confirmed: boolean) => apiPost<DatabaseTransferTask>(`${transfers}${id}/confirm/`, { conflictPolicy, confirmed });
export const cancelDatabaseTransfer = (id: string) => apiPost<DatabaseTransferTask>(`${transfers}${id}/cancel/`, {});
export const retryDatabaseTransfer = (id: string, confirmed: boolean) => apiPost<DatabaseTransferTask>(`${transfers}${id}/retry/`, { confirmed });
export const deleteDatabaseTransfer = (id: string) => apiDelete<{ deleted: boolean }>(`${transfers}${id}/delete/`);
export const databaseTransferDownloadUrl = (id: string) => `${transfers}${id}/download/`;
export async function apiRequestTransfer<T>(url: string, method: string, body: BodyInit): Promise<T> {
  const response = await fetch(url, { method, body, credentials: 'include' });
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.error || data.detail || '上传分片失败'); }
  return (response.status === 204 ? undefined : response.json()) as Promise<T>;
}
