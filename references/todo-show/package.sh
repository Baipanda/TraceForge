#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_ROOT"

APP_NAME="todo_show"
VERSION=$(date +"%Y%m%d_%H%M%S")
RELEASE_DIR="$PROJECT_ROOT/release"
PACKAGE_NAME="${APP_NAME}_${VERSION}.tar.gz"
PACKAGE_PATH="$RELEASE_DIR/$PACKAGE_NAME"

mkdir -p "$RELEASE_DIR"

echo "Todo Show Docker 部署包打包"
echo "项目目录: $PROJECT_ROOT"
echo "输出文件: $PACKAGE_PATH"

tar \
  --exclude="./release" \
  --exclude="./.git" \
  --exclude="./.env" \
  --exclude="./.venv" \
  --exclude="./backend/__pycache__" \
  --exclude="./backend/.pytest_cache" \
  --exclude="./frontend/node_modules" \
  --exclude="./frontend/dist" \
  --exclude="./frontend/.vite" \
  --exclude="./*.pyc" \
  -czf "$PACKAGE_PATH" \
  .

echo ""
echo "打包完成:"
echo "  $PACKAGE_PATH"
echo ""
echo "上传到服务器示例:"
echo "  scp \"$PACKAGE_PATH\" user@server:/opt/"
echo ""
echo "服务器部署示例:"
echo "  cd /opt"
echo "  mkdir -p todo_show"
echo "  tar -xzf \"$PACKAGE_NAME\" -C todo_show"
echo "  cd todo_show"
echo "  cp .env.example .env"
echo "  vi .env"
echo "  sh deploy.sh"
