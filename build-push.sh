#!/bin/bash

set -e

# ==============================
# 配置
# ==============================
PROJECT_DIR="/opt/devops-captain"
BUILD_SCRIPT_DIR="${PROJECT_DIR}/deploy/scripts"
IMAGE_REPO="registry.cn-beijing.aliyuncs.com/kaikai136/devops-captain"

# ==============================
# 参数
# ==============================
GIT_BRANCH="$1"
VERSION="$2"

# ==============================
# 参数检查
# ==============================
if [ -z "${GIT_BRANCH}" ] || [ -z "${VERSION}" ]; then
    echo "错误：请指定 Git 分支和镜像版本"
    echo
    echo "使用方法："
    echo "  $0 <Git分支> <镜像版本>"
    echo
    echo "例如："
    echo "  $0 Element_update v1.0.0"
    echo "  $0 master v1.0.1"
    exit 1
fi

IMAGE="${IMAGE_REPO}:${VERSION}"

echo "========================================"
echo " DevOps Tools 镜像构建"
echo "========================================"
echo "项目目录 : ${PROJECT_DIR}"
echo "Git 分支 : ${GIT_BRANCH}"
echo "镜像版本 : ${VERSION}"
echo "镜像地址 : ${IMAGE}"
echo "========================================"

# ==============================
# 1. 更新代码
# ==============================
echo
echo "[1/3] 更新 Git 仓库..."

cd "${PROJECT_DIR}"

echo "拉取远程仓库信息..."
git fetch origin

# 检查远程分支是否存在
if ! git show-ref --verify --quiet "refs/remotes/origin/${GIT_BRANCH}"; then
    echo
    echo "错误：远程分支不存在：origin/${GIT_BRANCH}"
    echo
    echo "当前远程分支："
    git branch -r
    exit 1
fi

echo "切换到分支：${GIT_BRANCH}"

# -B:
#   分支不存在 -> 创建
#   分支已存在 -> 重置到 origin/GIT_BRANCH
#   detached HEAD -> 也可以正常切换
git checkout -B "${GIT_BRANCH}" "origin/${GIT_BRANCH}"

echo
echo "Git 更新完成"
echo "当前分支：$(git branch --show-current)"
echo "当前 Commit："
git log -1 --oneline

# ==============================
# 2. 构建镜像
# ==============================
echo
echo "[2/3] 构建 Docker 镜像..."
echo "镜像：${IMAGE}"

cd "${BUILD_SCRIPT_DIR}"

bash build-image.sh "${IMAGE}"

# ==============================
# 3. 推送镜像
# ==============================
echo
echo "[3/3] 推送 Docker 镜像..."
echo "镜像：${IMAGE}"

docker push "${IMAGE}"

# ==============================
# 完成
# ==============================
echo
echo "========================================"
echo " 构建并推送完成"
echo "========================================"
echo "Git 分支 : ${GIT_BRANCH}"
echo "Git Commit: $(git -C "${PROJECT_DIR}" rev-parse --short HEAD)"
echo "镜像      : ${IMAGE}"
echo "========================================"