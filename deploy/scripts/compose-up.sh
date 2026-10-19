#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
deploy="$root/deploy"
mkdir -p "$deploy/data/static"
[ -f "$deploy/config/app.conf" ] || cp "$deploy/config/app.conf.example" "$deploy/config/app.conf"
docker compose -f "$deploy/docker-compose.yml" up -d --build
docker compose -f "$deploy/docker-compose.yml" ps
