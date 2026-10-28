"""Finish only the exact test asset/task previously created in this session."""
import csv
import io
import json
from pathlib import Path


def finish_probe(client, task_id, asset_id, filename):
    base = 'http://172.16.0.161:30000/api/database-management/'
    headers = {'X-CSRFToken': client.cookies.get('csrftoken'), 'Referer': 'http://172.16.0.161:30000/'}
    task = client.get(base+f'transfers/{task_id}/').json()
    assert task['status'] == 'succeeded' and task['assetId'] == asset_id
    asset = client.get(base+'assets/').json()
    matching = [a for a in asset if a['id'] == asset_id and a['options'].get('file') == filename and a['name'].startswith('perf_')]
    assert len(matching) == 1
    download = client.get(base+f'transfers/{task_id}/download/', timeout=30)
    download.raise_for_status()
    rows = list(csv.reader(io.StringIO(download.content.decode('utf-8-sig'))))
    assert len(rows) == 10001 and rows[0] == ['id', 'value']
    assert [int(row[0]) for row in rows[1:]] == list(range(1, 10001))
    result = {'task': task, 'download_status': download.status_code, 'bytes': len(download.content), 'verified_rows': len(rows)-1, 'cleanup': []}
    for method, path, payload in [
        ('DELETE', f'transfers/{task_id}/delete/', None),
        ('POST', f'assets/{asset_id}/database/', {'action': 'delete', 'name': filename}),
        ('DELETE', f'assets/{asset_id}/', None),
    ]:
        r = client.request(method, base+path, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        result['cleanup'].append({'path': path, 'status': r.status_code})
    result['remaining_assets'] = len(client.get(base+'assets/').json())
    Path('docs/performance/2026-10-23-export-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
