import type { DatabaseAsset, DatabaseAssetPayload, MysqlConnectionOptions } from '../api/databaseManagement';

export const connectionColors = ['#ff4d4f', '#fa8c16', '#fadb14', '#52c41a', '#36cfc9', '#1890ff', '#9254de', '#8c8c8c'];
export const environments: Record<string, string> = { development: '开发', test: '测试', staging: '预发布', production: '生产' };
export const parameterLabels: Record<string, string> = { readTimeout: '读取超时（秒）', writeTimeout: '写入超时（秒）', autocommit: '自动提交', sqlMode: 'SQL 模式', timeZone: '会话时区' };
export const sqlModes = 'ALLOW_INVALID_DATES ANSI ANSI_QUOTES ERROR_FOR_DIVISION_BY_ZERO HIGH_NOT_PRECEDENCE IGNORE_SPACE NO_AUTO_VALUE_ON_ZERO NO_BACKSLASH_ESCAPES NO_DIR_IN_CREATE NO_ENGINE_SUBSTITUTION NO_UNSIGNED_SUBTRACTION NO_ZERO_DATE NO_ZERO_IN_DATE ONLY_FULL_GROUP_BY PAD_CHAR_TO_FULL_LENGTH PIPES_AS_CONCAT REAL_AS_FLOAT STRICT_ALL_TABLES STRICT_TRANS_TABLES TRADITIONAL TIME_TRUNCATE_FRACTIONAL NO_AUTO_CREATE_USER'.split(' ');
export function mysqlDraft(asset?: DatabaseAsset | null, directoryId?: number | null) {
  const previous = JSON.parse(JSON.stringify(asset?.options || {}));
  const options: MysqlConnectionOptions = {
    color: '', environment: '', readOnly: false, expiresAt: null, authMethod: 'password', connectTimeout: 5, charset: 'auto',
    ...previous,
    parameters: { ...(previous.parameters as object || {}) },
    ssh: { enabled: false, host: '', port: 22, username: '', authMethod: 'password', ...(previous.ssh as object || {}) },
    ssl: Boolean(previous.ssl), tls: { mode: 'require', ...(previous.tls as object || {}) },
  };
  const form: DatabaseAssetPayload = { applicationKeyId: asset?.applicationKeyId ?? null, name: asset?.name || '', directoryId: asset?.directoryId ?? directoryId ?? null, dbType: 'mysql', host: asset?.host || '', port: asset?.port || 3306, username: asset?.username || '', password: '', databaseName: asset?.databaseName || '', remark: asset?.remark || '', options, connectionSecrets: {} };
  return { form, options };
}
export function connectionExpired(asset?: DatabaseAsset | null) {
  return asset?.dbType === 'mysql' && Boolean(asset.options.expiresAt) && Date.parse(String(asset.options.expiresAt)) <= Date.now();
}
export function connectionCan(asset: DatabaseAsset | null | undefined, action: string) {
  if (asset?.dbType !== 'mysql') return true;
  if (['create', 'edit', 'delete', 'view'].includes(action)) return true;
  if (connectionExpired(asset)) return false;
  return !(asset.options.readOnly && ['modify_data', 'manage_schema', 'database_admin', 'write_accounts', 'import_data'].includes(action));
}
