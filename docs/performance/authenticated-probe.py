"""Run from an authenticated operator session: run_probe(requests_session, host_ids).
Does not store cookies, credentials, host addresses, or response bodies.
"""
import concurrent.futures as futures
import json
import subprocess
import time
from pathlib import Path

BASE = 'http://172.16.0.161:30000'
OUTPUT = Path('docs/performance/2026-10-23-authenticated-results.json')


def run_probe(session, host_ids):
    import requests
    import websocket
    result = {'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'stages': [], 'samples': []}
    cookies = dict(session.cookies)

    def save():
        OUTPUT.write_text(json.dumps(result, indent=2), encoding='utf-8')

    def sample(label):
        p = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                            'root@172.16.0.161', 'kubectl top pods -n middleware --containers; kubectl top nodes; kubectl get pods -n middleware'],
                           capture_output=True, text=True, timeout=25)
        result['samples'].append({'label': label, 'elapsed_s': round(time.monotonic()-start, 2), 'metrics': p.stdout, 'exit': p.returncode})
        save()

    def fetch(path, method='GET'):
        t = time.monotonic()
        try:
            r = requests.request(method, BASE+path, cookies=cookies, timeout=20)
            return {'status': r.status_code, 'ms': round((time.monotonic()-t)*1000, 2)}
        except Exception as exc:
            return {'status': type(exc).__name__, 'ms': round((time.monotonic()-t)*1000, 2)}

    def summary(label, rows, elapsed):
        times = sorted(r['ms'] for r in rows)
        codes = {}
        for r in rows:
            k = str(r['status']); codes[k] = codes.get(k, 0)+1
        result['stages'].append({'label': label, 'requests': len(rows), 'codes': codes,
                                 'elapsed_s': round(elapsed, 2), 'rps': round(len(rows)/elapsed, 2),
                                 'p50_ms': times[int((len(times)-1)*.5)], 'p95_ms': times[int((len(times)-1)*.95)], 'max_ms': times[-1]})
        save()

    start = time.monotonic()
    sample('baseline')
    for path in ['/', '/api/health/', '/api/auth/me/']:
        for concurrency in [10, 25, 50]:
            t = time.monotonic()
            with futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                rows = list(pool.map(fetch, [path]*(concurrency*5)))
            summary(f'{path} concurrency={concurrency}', rows, time.monotonic()-t)
            sample(f'{path} concurrency={concurrency}')
    for round_no in range(3):
        t = time.monotonic()
        with futures.ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(lambda p: fetch(p, 'POST'), [f'/api/web-terminal/hosts/{i}/monitor/' for i in host_ids]))
        summary(f'four-host-monitor round={round_no+1}', rows, time.monotonic()-t)
        sample(f'monitor-{round_no+1}')

    def terminal(host_id):
        t = time.monotonic(); ws = None
        try:
            ws = websocket.create_connection(BASE.replace('http:', 'ws:')+f'/ws/web-terminal/{host_id}/',
                                            cookie='; '.join(f'{k}={v}' for k,v in cookies.items()), timeout=15)
            banner = ''
            while len(banner) < 20:
                banner += str(ws.recv())
            return {'status': 'banner_received', 'ms': round((time.monotonic()-t)*1000, 2)}
        except Exception as exc:
            return {'status': type(exc).__name__, 'ms': round((time.monotonic()-t)*1000, 2)}
        finally:
            if ws is not None: ws.close()
    t = time.monotonic()
    with futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(terminal, host_ids))
    summary('four-real-SSH-terminal-connections', rows, time.monotonic()-t)
    sample('after-SSH')
    t = time.monotonic(); rows = []; next_monitor = t
    while time.monotonic()-t < 300:
        rows.append(fetch('/api/auth/me/'))
        if time.monotonic() >= next_monitor:
            monitor_start = time.monotonic()
            with futures.ThreadPoolExecutor(max_workers=4) as pool:
                monitor_rows = list(pool.map(lambda p: fetch(p, 'POST'), [f'/api/web-terminal/hosts/{i}/monitor/' for i in host_ids]))
            summary('stability-four-host-monitor', monitor_rows, time.monotonic()-monitor_start)
            sample('stability')
            next_monitor += 30
        time.sleep(min(1, max(0, next_monitor-time.monotonic())))
    summary('five-minute-authenticated-stability', rows, time.monotonic()-t)
    sample('final')
    result['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z'); save()
