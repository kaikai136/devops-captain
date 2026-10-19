#!/bin/sh
set -eu
cd "$(dirname "$0")/../../.."
sh -n deploy/backend-entrypoint.sh
bash -n deploy/scripts/compose-up.sh deploy/scripts/build-image.sh publish-images.sh
bash publish-images.sh test --dry-run
if command -v docker >/dev/null 2>&1; then docker compose -f deploy/docker-compose.yml config >/dev/null; else echo "Docker unavailable: compose validation skipped"; fi
test ! -e deploy/Dockerfile
test ! -e deploy/docker/entrypoint.sh
grep -q "DJANGO_STATIC_ROOT=/data/static" deploy/config/app.conf
grep -q "Generated and persisted" deploy/backend-entrypoint.sh
echo "Deployment checks passed"
