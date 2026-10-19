#!/bin/sh
set -eu

TAG=latest
KEEP_IMAGES=false
DRY_RUN=false
TAG_SET=false

usage() {
    printf '%s\n' 'Usage: sh publish-images.sh [TAG] [--keep-images] [--dry-run]'
}

for argument in "$@"; do
    case "$argument" in
        --keep-images) KEEP_IMAGES=true ;;
        --dry-run) DRY_RUN=true ;;
        -h|--help) usage; exit 0 ;;
        -*) usage >&2; exit 2 ;;
        *)
            if [ "$TAG_SET" = true ]; then
                usage >&2
                exit 2
            fi
            TAG=$argument
            TAG_SET=true
            ;;
    esac
done

case "$TAG" in
    ''|[!a-zA-Z0-9_]*|*[!a-zA-Z0-9_.-]*)
        printf '%s\n' 'Invalid Docker image tag.' >&2
        exit 2
        ;;
esac
if [ "${#TAG}" -gt 128 ]; then
    printf '%s\n' 'Docker image tag must not exceed 128 characters.' >&2
    exit 2
fi

SCRIPT_DIR=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

REGISTRY=registry.cn-beijing.aliyuncs.com/kaikai136
BACKEND_IMAGE="$REGISTRY/devops-tools-backend:$TAG"
FRONTEND_IMAGE="$REGISTRY/devops-tools-frontend:$TAG"

run_docker() {
    printf 'docker'
    printf ' %s' "$@"
    printf '\n'
    if [ "$DRY_RUN" = false ]; then
        docker "$@"
    fi
}

if [ "$DRY_RUN" = false ] && ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' 'Docker is not installed or is not available in PATH.' >&2
    exit 1
fi

run_docker build -f deploy/backend.Dockerfile -t "$BACKEND_IMAGE" .
run_docker build -f deploy/frontend.Dockerfile -t "$FRONTEND_IMAGE" .
run_docker push "$BACKEND_IMAGE"
run_docker push "$FRONTEND_IMAGE"

if [ "$KEEP_IMAGES" = false ]; then
    run_docker rmi "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
fi

if [ "$DRY_RUN" = true ]; then
    printf '%s\n' 'Dry run completed. No Docker commands were executed.'
else
    printf 'Published backend and frontend images with tag: %s\n' "$TAG"
fi
