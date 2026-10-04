import { describe, expect, it, vi } from 'vitest';
import { buildDatabaseTreeMenu, type DatabaseTreeMenuTarget } from '../components/databaseTreeMenu';

const permissions = new Set(['create', 'edit', 'delete', 'manage_schema', 'execute_sql', 'view_data', 'import_export', 'database_admin', 'manage_accounts', 'test_connection']);

function menu(target: DatabaseTreeMenuTarget, options: { dbType?: string; capabilities?: string[]; selectedCount?: number } = {}) {
  return buildDatabaseTreeMenu(target, {
    connected: true,
    dbType: options.dbType || 'mysql',
    capabilities: options.capabilities || ['accounts', 'routines', 'optimize', 'truncate', 'rename_view'],
    selectedCount: options.selectedCount || 0,
    pinned: false,
    can: action => permissions.has(action),
    run: vi.fn(),
  });
}

function byId(items: ReturnType<typeof menu>, id: string) {
  const item = items.find(entry => entry.id === id);
  expect(item, `missing menu item ${id}`).toBeTruthy();
  return item!;
}

describe('HexHub database tree menus', () => {
  it('guards query mutation and file operations independently', () => {
    const entries = buildDatabaseTreeMenu({ kind: 'query', name: 'report', category: 'query' }, { connected: true, dbType: 'mysql', capabilities: [], selectedCount: 0, pinned: false, can: action => action === 'view_data', run: vi.fn() });
    expect(byId(entries, 'open-query').enabled).toBe(true);
    expect(byId(entries, 'copy-query').enabled).toBe(true);
    for (const id of ['cut-query', 'paste-query', 'rename-query', 'delete-query', 'toggle-query-pin']) expect(byId(entries, id).enabled).toBe(false);
    expect(byId(entries, 'query-transfer').children?.every(item => !item.enabled)).toBe(true);
  });

  it('keeps Redis database nodes out of relational menus', () => {
    expect(menu({ kind: 'database', name: '0' }, { dbType: 'redis' }).map(item => item.id)).toEqual(['open', 'refresh']);
  });

  it('disables unsafe routine edits and unsupported actual routine actions', () => {
    expect(byId(menu({ kind: 'object', category: 'function', name: 'f' }), 'edit-object-definition').enabled).toBe(false);
    const entries = menu({ kind: 'object', category: 'function', name: 'f' }, { dbType: 'sqlite', capabilities: [] });
    for (const id of ['open-object', 'edit-object-definition', 'copy-ddl', 'drop-object']) expect(byId(entries, id).enabled).toBe(false);
  });
  it('builds the connection menu with account management and more actions', () => {
    const items = menu({ kind: 'asset', name: 'MySQL', assetId: 1 });
    expect(items.map(item => item.label)).toEqual([
      '关闭', '刷新', '编辑', '克隆', '复制Host', '新建目录', '新建连接', '新建数据库连接',
      '重命名', '删除', '账号管理', '新建数据库', '导入数据库', '导出数据库', '更多',
    ]);
    expect(byId(items, 'more').children?.map(item => item.label)).toEqual(['测试连接', '移动', '导出连接', '断开']);
  });

  it('keeps unfinished table-category features visible and disabled', () => {
    const items = menu({ kind: 'category', name: 'table', category: 'table' }, { selectedCount: 2 });
    expect(byId(items, 'new-table').shortcut).toBe('Ctrl+Shift+T');
    expect(byId(items, 'new-query').shortcut).toBe('Ctrl+Shift+Q');
    for (const id of ['new-object-folder', 'data-transfer', 'sync', 'sql-history']) expect(byId(items, id).enabled).toBe(false);
    expect(byId(items, 'delete-selected').enabled).toBe(true);
  });

  it('builds destructive actions and SQL-only transfers for an actual table', () => {
    const items = menu({ kind: 'object', name: 'orders', category: 'table' });
    expect(byId(items, 'open-data').shortcut).toBe('Enter');
    expect(byId(items, 'rename-object').shortcut).toBe('F2');
    expect(byId(items, 'delete-object-menu').children?.map(item => item.id)).toEqual(['drop-object', 'delete-rows', 'truncate-table']);
    expect(byId(items, 'export-sql').enabled).toBe(true);
    expect(items.some(item => item.id === 'export-csv')).toBe(false);
    for (const dbType of ['sqlite', 'postgresql', 'clickhouse']) {
      const unsupported = menu({ kind: 'object', name: 'orders', category: 'table' }, { dbType });
      expect(byId(unsupported, 'export-sql').enabled).toBe(false);
      expect(byId(unsupported, 'import-table').enabled).toBe(false);
    }
  });

  it('enables actual view actions while disabling virtual folders', () => {
    const category = menu({ kind: 'category', name: 'view', category: 'view' });
    const object = menu({ kind: 'object', name: 'active_users', category: 'view' });
    expect(byId(category, 'open-object').enabled).toBe(false);
    expect(byId(object, 'open-object').enabled).toBe(true);
    expect(byId(object, 'edit-object-definition').enabled).toBe(true);
    expect(byId(object, 'rename-object').enabled).toBe(true);
    expect(byId(object, 'new-object-folder').enabled).toBe(false);
  });

  it('builds query clipboard and SQL file actions', () => {
    const items = menu({ kind: 'query', name: 'daily report', category: 'query', queryId: 3 });
    expect(byId(items, 'copy-query').shortcut).toBe('Ctrl+C');
    expect(byId(items, 'cut-query').shortcut).toBe('Ctrl+X');
    expect(byId(items, 'paste-query').shortcut).toBe('Ctrl+V');
    expect(byId(items, 'delete-query').shortcut).toBe('Backspace');
    expect(byId(items, 'query-transfer').children?.map(item => item.id)).toEqual(['export-query', 'import-query']);
  });

  it('uses capabilities to disable unsupported accounts and routines', () => {
    const sqliteConnection = menu({ kind: 'asset', name: 'SQLite', assetId: 2 }, { dbType: 'sqlite', capabilities: [] });
    const sqliteRoutine = menu({ kind: 'category', name: 'function', category: 'function' }, { dbType: 'sqlite', capabilities: [] });
    const clickhouseRoutine = menu({ kind: 'category', name: 'procedure', category: 'procedure' }, { dbType: 'clickhouse', capabilities: ['accounts'] });
    expect(byId(sqliteConnection, 'accounts').enabled).toBe(false);
    expect(byId(sqliteRoutine, 'new-function').enabled).toBe(false);
    expect(byId(clickhouseRoutine, 'new-procedure').enabled).toBe(false);
  });
});
