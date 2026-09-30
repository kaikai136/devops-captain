import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  executeDatabaseSql, getDatabaseIndexes, getDatabaseTableData, getDatabaseTree,
  getDatabaseDdl, getRedisKeys, getRedisValue, listDatabaseObjects, listDatabaseTypes, modifyDatabaseRow, modifyDatabaseSchema, testDatabaseAsset,
} from '../api/databaseManagement';

afterEach(() => vi.unstubAllGlobals());

function mockResponse(payload: unknown) {
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

describe('database management API', () => {
  it('scopes Redis keys and values to the selected DB', async () => {
    const fetch = mockResponse({ keys: [], counts: Array(16).fill(0) });
    await getRedisKeys(7, '*', 5);
    await getRedisValue(7, 'sample', 5);
    expect(fetch.mock.calls[0][0]).toContain('db=5');
    expect(fetch.mock.calls[1][0]).toContain('db=5');
  });
  it('loads connection types and tests an asset only on explicit request', async () => {
    const fetch = mockResponse({ types: [] });
    await listDatabaseTypes();
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe('/api/database-management/types/');

    fetch.mockClear();
    await testDatabaseAsset(7);
    expect(fetch.mock.calls[0][0]).toBe('/api/database-management/assets/7/test/');
    expect(fetch.mock.calls[0][1].method).toBe('POST');
  });

  it('keeps database, schema, filtering and paging scoped to the selected asset', async () => {
    const fetch = mockResponse({ databases: [], schemas: [] });
    await getDatabaseTree(7, 'sales db');
    await getDatabaseTableData(7, {
      database: 'sales db', schema: 'public', table: 'orders',
      page: 2, pageSize: 25, sort: 'created_at', direction: 'desc',
      whereField: 'status', whereValue: 'open',
    });
    expect(fetch.mock.calls[0][0]).toContain('database=sales+db');
    expect(fetch.mock.calls[1][0]).toContain('/assets/7/data/');
    expect(fetch.mock.calls[1][0]).toContain('schema=public');
    expect(fetch.mock.calls[1][0]).toContain('page=2');
    expect(fetch.mock.calls[1][0]).toContain('whereValue=open');
  });

  it('loads normalized table metadata and a single-table DDL with scoped parameters', async () => {
    const fetch = mockResponse({ objects: [{ name: 'orders', data_length: null, index_length: 12 }] });
    await listDatabaseObjects(7, 'sales db', 'public', 'table');
    await getDatabaseDdl(7, 'sales db', 'orders', 'public');
    expect(fetch.mock.calls[0][0]).toContain('/assets/7/objects/');
    expect(fetch.mock.calls[0][0]).toContain('database=sales+db');
    expect(fetch.mock.calls[0][0]).toContain('type=table');
    expect(fetch.mock.calls[1][0]).toContain('/assets/7/ddl/');
    expect(fetch.mock.calls[1][0]).toContain('table=orders');
    expect(fetch.mock.calls[1][0]).toContain('schema=public');
  });

  it('passes the cancel signal to SQL requests and sends row edits separately', async () => {
    const fetch = mockResponse({ rows: [], affected: 0, columns: [], elapsedMs: 1 });
    const controller = new AbortController();
    await executeDatabaseSql(3, 'SELECT 1', 'main', controller.signal);
    expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ sql: 'SELECT 1', database: 'main' });

    await modifyDatabaseRow(3, { table: 'sample', action: 'update', key: { id: 1 }, values: { name: 'new' } });
    expect(fetch.mock.calls[1][0]).toBe('/api/database-management/assets/3/rows/');
    expect(JSON.parse(fetch.mock.calls[1][1].body).key).toEqual({ id: 1 });
  });

  it('scopes index inspection and structure edits to the selected asset', async () => {
    const fetch = mockResponse({ indexes: [] });
    await getDatabaseIndexes(9, 'main', 'sample', 'public');
    expect(fetch.mock.calls[0][0]).toContain('/assets/9/indexes/');
    expect(fetch.mock.calls[0][0]).toContain('schema=public');
    await modifyDatabaseSchema(9, { database: 'main', table: 'sample', action: 'add_column', name: 'status', columnType: 'TEXT' });
    expect(fetch.mock.calls[1][0]).toBe('/api/database-management/assets/9/schema/');
    expect(JSON.parse(fetch.mock.calls[1][1].body).action).toBe('add_column');
  });
});
