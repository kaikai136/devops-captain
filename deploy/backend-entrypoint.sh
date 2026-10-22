#!/bin/sh
set -eu
cd /app/backend

# Require explicit configuration, as in fileHub; never fall back to a dev key.
python - <<'PY'
from pathlib import Path
from ops_tool.settings import APP_CONFIG_FILE, APP_CONFIG, redis_config_path
if not Path(APP_CONFIG_FILE).is_file():
    raise SystemExit("Missing APP_CONFIG_FILE")
if not redis_config_path().is_file():
    raise SystemExit("Missing REDIS_CONFIG_FILE")
secret = APP_CONFIG.get("DJANGO_SECRET_KEY", "").strip().strip("\"'")
if len(secret) < 32 or secret.startswith("REPLACE_"):
    raise SystemExit("Set a unique DJANGO_SECRET_KEY (at least 32 characters) in app.conf")
PY

case "${1:-backend}" in
    backend)
        python manage.py migrate --noinput
        python manage.py collectstatic --noinput
        exec daphne -b 0.0.0.0 -p 8000 ops_tool.asgi:application
        ;;
    transfer-worker)
        # The backend performs migrations before becoming ready.
        python - <<'PY'
import time
from urllib.request import urlopen
from urllib.error import URLError
import os
url = os.environ.get("BACKEND_HEALTH_URL", "http://backend:8000/api/health/")
for attempt in range(120):
    try:
        with urlopen(url, timeout=3) as response:
            if response.status == 200:
                break
    except (URLError, TimeoutError, OSError):
        pass
    time.sleep(2)
else:
    raise SystemExit("Backend did not become healthy; worker not started")
PY
        exec python manage.py run_database_transfer_worker --poll-interval 1
        ;;
    *) exec "$@" ;;
esac
