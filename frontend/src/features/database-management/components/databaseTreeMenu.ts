import type { ContextMenuEntry } from '@shared/components/context-menu/types';
import type { IconName } from '@shared/components/AppIcon.vue';

export type DatabaseObjectCategory = 'table' | 'view' | 'procedure' | 'function';
export type DatabaseTreeMenuTarget = {
  kind: 'root' | 'directory' | 'asset' | 'database' | 'schema' | 'category' | 'object' | 'query' | 'redis';
  name: string;
  assetId?: number;
  directoryId?: number;
  category?: DatabaseObjectCategory | 'query';
  queryId?: number;
  signature?: string;
  database?: string;
  schema?: string;
};

export type DatabaseMenuContext = {
  connected: boolean;
  dbType: string;
  capabilities: string[];
  selectedCount: number;
  pinned: boolean;
  can: (action: string) => boolean;
  run: (action: string) => void | Promise<void>;
};

type ItemOptions = { enabled?: boolean; shortcut?: string; danger?: boolean; separatorBefore?: boolean; children?: ContextMenuEntry[] };

function item(context: DatabaseMenuContext, id: string, label: string, icon: IconName, options: ItemOptions = {}): ContextMenuEntry {
  const permissions: Record<string, string> = {
    'open-data': 'view_data', 'edit-structure': 'view_data', 'open-object': 'view_data', 'copy-ddl': 'view_data',
    'open-query': 'view_data', 'copy-query': 'view_data', 'toggle-query-pin': 'execute_sql',
    'rename-query': 'execute_sql', 'cut-query': 'execute_sql', 'paste-query': 'execute_sql', 'delete-query': 'execute_sql',
    'import-query': 'import_export', 'export-query': 'import_export',
  };
  const permission = permissions[id];
  return { id, label, icon, enabled: (options.enabled ?? true) && (!permission || context.can(permission)) && (id !== 'import-query' || context.can('execute_sql')), shortcut: options.shortcut, danger: options.danger,
    separatorBefore: options.separatorBefore, children: options.children, action: () => context.run(id) };
}

function disabled(context: DatabaseMenuContext, id: string, label: string, icon: IconName, separatorBefore = false) {
  return item(context, id, label, icon, { enabled: false, separatorBefore });
}

function commonDisabled(context: DatabaseMenuContext) {
  return [
    disabled(context, 'new-object-folder', '新建目录', 'folderPlus'),
    disabled(context, 'data-transfer', '数据传输', 'databaseBackup', true),
    disabled(context, 'sync', '同步', 'refresh'),
    disabled(context, 'sql-history', 'SQL执行历史', 'history'),
  ];
}

export function buildDatabaseTreeMenu(target: DatabaseTreeMenuTarget, context: DatabaseMenuContext): ContextMenuEntry[] {
  const manageSchema = context.can('manage_schema');
  const importExport = context.can('import_export');
  const supports = (capability: string) => context.capabilities.includes(capability);
  if (context.dbType === 'redis' && target.kind === 'database') return [item(context, 'open', '打开', 'eye'), item(context, 'refresh', '刷新', 'refresh', { shortcut: 'F5' })];
  if (target.kind === 'root' || target.kind === 'directory') return [
    item(context, 'new-folder', '新建目录', 'folderPlus', { enabled: context.can('create') }),
    item(context, 'new-connection', '新建连接', 'link', { enabled: context.can('create') }),
    item(context, 'rename-folder', '重命名', 'edit', { enabled: target.kind === 'directory' && context.can('edit') }),
    item(context, 'move-folder', '移动目录', 'moveRight', { enabled: target.kind === 'directory' && context.can('edit') }),
    item(context, 'copy-folder', '复制目录', 'copy', { enabled: target.kind === 'directory' && context.can('create') }),
    item(context, 'import-connections', '导入连接', 'upload', { enabled: importExport, separatorBefore: true }),
    item(context, 'export-connections', '导出连接', 'download', { enabled: importExport }),
    item(context, 'delete-folder', '删除目录', 'trash', { enabled: target.kind === 'directory' && context.can('delete'), danger: true }),
    item(context, 'refresh', '刷新', 'refresh'),
  ];
  if (target.kind === 'asset') return [
    item(context, 'close', '关闭', 'x'),
    item(context, 'refresh', '刷新', 'refresh'),
    item(context, 'edit', '编辑', 'edit', { enabled: context.can('edit') }),
    item(context, 'clone', '克隆', 'copy', { enabled: context.can('create') }),
    item(context, 'copy-host', '复制Host', 'clipboard', { enabled: context.can('create') }),
    item(context, 'new-folder', '新建目录', 'folderPlus', { enabled: context.can('create'), separatorBefore: true }),
    item(context, 'new-connection', '新建连接', 'link', { enabled: context.can('create') }),
    item(context, 'new-database-connection', '新建数据库连接', 'database', { enabled: context.can('create') }),
    item(context, 'rename-asset', '重命名', 'edit', { enabled: context.can('edit') }),
    item(context, 'delete-asset', '删除', 'trash', { enabled: context.can('delete'), danger: true }),
    item(context, 'accounts', '账号管理', 'userCog', { enabled: context.can('manage_accounts') && supports('accounts'), separatorBefore: true }),
    item(context, 'database-create', '新建数据库', 'database', { enabled: context.can('database_admin') }),
    item(context, 'database-import', '导入数据库', 'upload', { enabled: importExport }),
    item(context, 'database-export', '导出数据库', 'download', { enabled: importExport }),
    item(context, 'more', '更多', 'menu', { children: [
      item(context, 'test', '测试连接', 'circleCheck', { enabled: context.can('test_connection') }),
      item(context, 'move-asset', '移动', 'moveRight', { enabled: context.can('edit') }),
      item(context, 'export-connections', '导出连接', 'download', { enabled: importExport }),
      item(context, 'disconnect', '断开', 'link', { enabled: context.connected }),
    ] }),
  ];
  if (target.kind === 'database') return [
    item(context, 'new-table', '新建表', 'database', { enabled: manageSchema, shortcut: 'Ctrl+Shift+T' }),
    item(context, 'new-query', '新建查询', 'search', { enabled: context.can('execute_sql'), shortcut: 'Ctrl+Shift+Q' }),
    disabled(context, 'new-object-folder', '新建目录', 'folderPlus'),
    item(context, 'refresh', '刷新', 'refresh', { shortcut: 'F5' }),
    ...commonDisabled(context).slice(1),
    item(context, 'delete-selected', '删除', 'trash', { enabled: manageSchema && context.selectedCount > 0, danger: true }),
    item(context, 'database-export', '导出', 'download', { enabled: importExport }),
    item(context, 'database-import', '导入', 'upload', { enabled: importExport }),
  ];
  if (target.kind === 'category' && target.category === 'table') return buildDatabaseTreeMenu({ ...target, kind: 'database' }, context);
  if (target.kind === 'object' && target.category === 'table') return [
    item(context, 'open-data', '打开数据', 'eye', { shortcut: 'Enter' }),
    item(context, 'edit-structure', '编辑结构', 'settings', { shortcut: 'Ctrl+Shift+S' }),
    item(context, 'toggle-pin', context.pinned ? '取消置顶' : '点击置顶', 'pin'),
    item(context, 'new-table', '新建表', 'database', { enabled: manageSchema, shortcut: 'Ctrl+Shift+T' }),
    item(context, 'new-query', '新建查询', 'search', { enabled: context.can('execute_sql'), shortcut: 'Ctrl+Shift+Q' }),
    disabled(context, 'new-object-folder', '新建目录', 'folderPlus'),
    item(context, 'rename-object', '重命名', 'edit', { enabled: manageSchema, shortcut: 'F2' }),
    item(context, 'refresh', '刷新', 'refresh', { shortcut: 'F5' }),
    item(context, 'optimize-table', '优化表', 'zap', { enabled: manageSchema && supports('optimize') }),
    item(context, 'copy-ddl', '复制 DDL', 'clipboard'),
    ...commonDisabled(context).slice(1),
    item(context, 'delete-object-menu', '删除', 'trash', { enabled: manageSchema, danger: true, children: [
      item(context, 'drop-object', '删除表', 'trash', { enabled: manageSchema, danger: true }),
      item(context, 'delete-rows', '清空数据', 'trash', { enabled: manageSchema, danger: true }),
      item(context, 'truncate-table', '快速清空数据', 'zap', { enabled: manageSchema && supports('truncate'), danger: true }),
    ] }),
    item(context, 'export-table', '导出', 'download', { enabled: importExport, children: [
      item(context, 'export-csv', '导出 CSV', 'download', { enabled: importExport }),
      item(context, 'export-sql', '表结构及数据 SQL', 'fileCode', { enabled: importExport }),
      item(context, 'copy-ddl', '表结构 SQL', 'clipboard', { enabled: importExport }),
    ] }),
    item(context, 'import-table', '导入', 'upload', { enabled: importExport }),
  ];
  if (target.category === 'view') return [
    item(context, 'open-object', '打开视图', 'eye', { enabled: target.kind === 'object', shortcut: 'Enter' }),
    item(context, 'edit-object-definition', '编辑视图结构', 'settings', { enabled: target.kind === 'object' && manageSchema, shortcut: 'Ctrl+Shift+S' }),
    item(context, 'new-view', '新建视图', 'database', { enabled: manageSchema }),
    disabled(context, 'new-object-folder', '新建目录', 'folderPlus'),
    item(context, 'copy-ddl', '复制SQL', 'clipboard', { enabled: target.kind === 'object' }),
    disabled(context, 'copy-object', '复制', 'copy'), disabled(context, 'paste-object', '粘贴', 'clipboard'),
    item(context, 'rename-object', '重命名', 'edit', { enabled: target.kind === 'object' && manageSchema && supports('rename_view'), shortcut: 'F2' }),
    item(context, 'drop-object', '删除', 'trash', { enabled: target.kind === 'object' && manageSchema, danger: true }),
    item(context, 'refresh', '刷新', 'refresh', { shortcut: 'F5' }),
  ];
  if (target.category === 'query' || target.kind === 'query') return [
    item(context, 'open-query', '打开查询', 'fileCode', { enabled: target.kind === 'query', shortcut: 'Enter' }),
    item(context, 'toggle-query-pin', context.pinned ? '取消置顶' : '点击置顶', 'pin', { enabled: target.kind === 'query' }),
    item(context, 'new-query', '新建查询', 'search', { enabled: context.can('execute_sql'), shortcut: 'Ctrl+Shift+Q' }),
    disabled(context, 'new-object-folder', '新建目录', 'folderPlus'),
    item(context, 'rename-query', '重命名', 'edit', { enabled: target.kind === 'query', shortcut: 'F2' }),
    item(context, 'copy-query', '复制', 'copy', { enabled: target.kind === 'query', shortcut: 'Ctrl+C' }),
    item(context, 'cut-query', '剪切', 'scissors', { enabled: target.kind === 'query', shortcut: 'Ctrl+X' }),
    item(context, 'paste-query', '粘贴', 'clipboard', { enabled: true, shortcut: 'Ctrl+V' }),
    item(context, 'query-transfer', '查询导入/导出', 'databaseBackup', { children: [
      item(context, 'export-query', '导出为 SQL 文件', 'download', { enabled: target.kind === 'query' }),
      item(context, 'import-query', '导入 SQL 文件为查询', 'upload'),
    ] }),
    item(context, 'delete-query', '删除', 'trash', { enabled: target.kind === 'query', shortcut: 'Backspace', danger: true }),
    item(context, 'refresh-queries', '刷新', 'refresh', { shortcut: 'F5' }),
  ];
  if (target.category === 'function' || target.category === 'procedure') return [
    item(context, 'open-object', '打开', 'eye', { enabled: target.kind === 'object' && supports('routines'), shortcut: 'Enter' }),
    item(context, 'edit-object-definition', '编辑定义', 'settings', { enabled: target.kind === 'object' && manageSchema && supports('replace_routine'), shortcut: 'Ctrl+Shift+S' }),
    item(context, 'new-function', '新建函数', 'fileCode', { enabled: manageSchema && supports('routines') }),
    item(context, 'new-procedure', '新建存储过程', 'fileCode', { enabled: manageSchema && supports('routines') }),
    disabled(context, 'new-object-folder', '新建目录', 'folderPlus'),
    item(context, 'copy-ddl', '复制SQL', 'clipboard', { enabled: target.kind === 'object' && supports('routines') }),
    disabled(context, 'copy-object', '复制', 'copy'),
    item(context, 'rename-object', '重命名', 'edit', { enabled: target.kind === 'object' && manageSchema && supports('rename_routine'), shortcut: 'F2' }),
    item(context, 'drop-object', '删除', 'trash', { enabled: target.kind === 'object' && manageSchema && supports('routines'), danger: true }),
    item(context, 'refresh', '刷新', 'refresh', { shortcut: 'F5' }),
  ];
  return [item(context, 'open', '打开', 'eye'), item(context, 'refresh', '刷新', 'refresh')];
}
