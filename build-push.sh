#!/bin/bash

set -e

# ==============================
# 配置
# ==============================
PROJECT_DIR="/opt/devops-captain"
BUILD_SCRIPT_DIR="${PROJECT_DIR}/deploy/scripts"
IMAGE_REPO="registry.cn-beijing.aliyuncs.com/kaikai136/devops-captain"

# ==============================
# 参数检查
# ==============================
VERSION="$1"

if [ -z "${VERSION}" ]; then
    echo "错误：请指定镜像版本"
    echo
    echo "使用方法："
    echo "  $0 v2.1.2"
    echo
    echo "例如："
    echo "  $0 v2.1.3"
    exit 1
fi

IMAGE="${IMAGE_REPO}:${VERSION}"

echo "========================================"
echo " DevOps Tools 镜像构建"
echo "========================================"
echo "项目目录 : ${PROJECT_DIR}"
echo "镜像地址 : ${IMAGE}"
echo "========================================"

# ==============================
# 1. 更新代码
# ==============================
echo
echo "[1/3] 更新 Git 仓库..."

cd "${PROJECT_DIR}"

git pull

# ==============================
# 2. 构建镜像
# ==============================
echo
echo "[2/3] 构建 Docker 镜像..."

cd "${BUILD_SCRIPT_DIR}"

bash build-image.sh "${IMAGE}"

# ==============================
# 3. 推送镜像
# ==============================
echo
echo "[3/3] 推送 Docker 镜像..."

docker push "${IMAGE}"

echo
echo "========================================"
echo " 构建并推送完成"
echo " 镜像：${IMAGE}"
echo "========================================"