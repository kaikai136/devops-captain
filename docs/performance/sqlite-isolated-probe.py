"""Isolated SQLite API validation; accepts an already authenticated httpx client."""
import json
import time
import uuid
from pathlib import Path


def run_sqlite_probe(client):
    base = 'http://172.16.0.161:30000/api/database-management/'
    name = 'perf_' + uuid.uuid4().hex[:12]
    filename = name + '.sqlite3'
    headers = {'X-CSRFToken': client.cookies.get('csrftoken'), 'Referer': 'http://172.16.0.161:30000/'}
    rows = []
    aid = None
    created = False

    def call(label, method, route, **kwargs):
        t = time.monotonic()
        r = client.request(method, base+route, headers=headers, timeout=30, **kwargs)
        rows.append({'label': label, 'status': r.status_code, 'ms': round((time.monotonic()-t)*1000, 2)})
        return r

    try:
        r = call('create-isolated-asset', 'POST', 'assets/', json={'name': name, 'dbType': 'sqlite', 'options': {'file': filename}})
        r.raise_for_status(); aid = r.json()['id']
        route = f'assets/{aid}/'
        r = call('create-isolated-file', 'POST', route+'database/', json={'action': 'create', 'name': filename})
        r.raise_for_status(); created = True
        r = call('create-table', 'POST', route+'sql/', json={'sql': 'CREATE TABLE perf_rows (id INTEGER PRIMARY KEY, value TEXT)'})
        r.raise_for_status()
        sql = "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<10000) INSERT INTO perf_rows SELECT x, printf('%0100d',x) FROM n"
        r = call('insert-10000-rows', 'POST', route+'sql/', json={'sql': sql}); r.raise_for_status()
        r = call('verify-10000-rows', 'POST', route+'sql/', json={'sql': 'SELECT COUNT(*) AS count FROM perf_rows'})
        r.raise_for_status(); rows[-1]['verification'] = r.json()
        t = time.monotonic(); r = client.get(base+f'assets/{aid}/export/?table=perf_rows&format=csv', headers=headers, timeout=30)
        rows.append({'label': 'direct-csv-export', 'status': r.status_code, 'ms': round((time.monotonic()-t)*1000), 'bytes': len(r.content)})
        t = time.monotonic(); r = client.get(base+f'assets/{aid}/export/?table=perf_rows&format=sql', headers=headers, timeout=30)
        rows.append({'label': 'sql-dump-limit-check', 'status': r.status_code, 'ms': round((time.monotonic()-t)*1000), 'message': r.json().get('detail', r.json().get('message', '')) if 'application/json' in r.headers.get('content-type', '') else 'download'})
        r.raise_for_status() if r.status_code < 400 else None
    finally:
        if aid is not None:
            r = call('cleanup-isolated-file', 'POST', f'assets/{aid}/database/', json={'action': 'delete', 'name': filename})
            r.raise_for_status()
            r = call('cleanup-isolated-asset', 'DELETE', f'assets/{aid}/')
            r.raise_for_status()
        Path('docs/performance/2026-10-23-sqlite-results.json').write_text(json.dumps({'asset_id': aid, 'file_created': created, 'steps': rows}, indent=2), encoding='utf-8')
