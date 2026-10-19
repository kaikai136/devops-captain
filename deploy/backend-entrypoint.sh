#!/usr/bin/env sh
set -eu

mkdir -p /data/config /data/data /data/media /data/recordings

APP_CONFIG_FILE="${APP_CONFIG_FILE:-/etc/devops-tools/app.conf}"

if [ ! -f "$APP_CONFIG_FILE" ]; then
  echo "Missing config file: $APP_CONFIG_FILE" >&2
  echo "Create data/config/app.conf on the host before starting the container." >&2
  exit 1
fi

read_config_value() {
  key="$1"
  file="${2:-$APP_CONFIG_FILE}"
  if [ ! -f "$file" ]; then
    return 0
  fi

  awk -v key="$key" '
    /^[[:space:]]*($|#)/ { next }
    index($0, "=") == 0 { next }
    {
      line = $0
      sub(/^[[:space:]]*/, "", line)
      name = line
      sub(/=.*/, "", name)
      sub(/[[:space:]]*$/, "", name)
      if (name == key) {
        value = line
        sub(/^[^=]*=/, "", value)
        sub(/^[[:space:]]*/, "", value)
        sub(/[[:space:]]*$/, "", value)
        print value
        exit
      }
    }
  ' "$file"
}

wait_for_database() {
  database_engine="$(read_config_value DATABASE_ENGINE)"
  database_engine="$(printf '%s' "$database_engine" | tr '[:upper:]' '[:lower:]')"
  if [ "$database_engine" != "mysql" ]; then
    return 0
  fi

  database_host="$(read_config_value DATABASE_HOST)"
  database_port="$(read_config_value DATABASE_PORT)"
  if [ -z "$database_host" ]; then
    database_host="127.0.0.1"
  fi
  if [ -z "$database_port" ]; then
    database_port="3306"
  fi

  echo "Waiting for MySQL at ${database_host}:${database_port}."
  python - "$database_host" "$database_port" <<'PY'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
deadline = time.monotonic() + 60
while True:
    try:
        with socket.create_connection((host, port), timeout=3):
            raise SystemExit(0)
    except OSError:
        if time.monotonic() >= deadline:
            raise
        time.sleep(2)
PY
}

SECRET_KEY_FILE="$(read_config_value DJANGO_SECRET_KEY_FILE)"
if [ -z "$SECRET_KEY_FILE" ]; then
  SECRET_KEY_FILE="/data/data/django-secret-key"
fi

CONFIG_SECRET_KEY="$(read_config_value DJANGO_SECRET_KEY)"
PERSISTED_SECRET=""

if [ -n "$CONFIG_SECRET_KEY" ]; then
  echo "Using DJANGO_SECRET_KEY from the config file."
elif [ -s "$SECRET_KEY_FILE" ]; then
  PERSISTED_SECRET="$(cat "$SECRET_KEY_FILE")"
  if [ -n "$PERSISTED_SECRET" ]; then
    echo "Using the persisted Django secret key."
  fi
fi

if [ -z "$CONFIG_SECRET_KEY" ] && [ -z "$PERSISTED_SECRET" ]; then
  umask 077
  secret_key_dir="$(dirname "$SECRET_KEY_FILE")"
  secret_key_tmp="${SECRET_KEY_FILE}.tmp.$$"
  trap 'rm -f "$secret_key_tmp"' EXIT HUP INT TERM
  mkdir -p "$secret_key_dir"
  python -c 'import secrets; print(secrets.token_urlsafe(64))' > "$secret_key_tmp"
  chmod 600 "$secret_key_tmp"
  mv "$secret_key_tmp" "$SECRET_KEY_FILE"
  trap - EXIT HUP INT TERM
  echo "Generated and persisted a new Django secret key."
fi

wait_for_database

# RUN_MIGRATE / RUN_COLLECTSTATIC let callers skip these steps.
# Defaults keep the docker-compose flow unchanged (both run). In Kubernetes
# migrations run in a dedicated initContainer and static files are baked into
# the image, so the app/worker containers set both to 0.
RUN_MIGRATE="${RUN_MIGRATE:-1}"
RUN_COLLECTSTATIC="${RUN_COLLECTSTATIC:-1}"

if [ "$RUN_MIGRATE" = "1" ]; then
  python manage.py migrate --noinput
else
  echo "Skipping migrations (RUN_MIGRATE=$RUN_MIGRATE)."
fi

if [ "$RUN_COLLECTSTATIC" = "1" ]; then
  python manage.py collectstatic --noinput
else
  echo "Skipping collectstatic (RUN_COLLECTSTATIC=$RUN_COLLECTSTATIC)."
fi

exec "$@"
