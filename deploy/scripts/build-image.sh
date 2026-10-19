#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DEPLOY_DIR/.." && pwd)"
IMAGE_NAME="${1:-devops-tools-backend:latest}"

docker build -f "$DEPLOY_DIR/backend.Dockerfile" -t "$IMAGE_NAME" "$REPO_ROOT"
