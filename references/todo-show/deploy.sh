#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_ROOT"

APP_NAME="Todo Show"

find_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    echo ""
  fi
}

echo "$APP_NAME 一键部署"
echo "项目目录: $PROJECT_ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo ""
  echo "未找到 docker 命令，请先在服务器安装 Docker。"
  exit 1
fi

COMPOSE=$(find_compose)
if [ -z "$COMPOSE" ]; then
  echo ""
  echo "未找到 docker compose 或 docker-compose，请先安装 Docker Compose。"
  exit 1
fi

if [ ! -f ".env" ]; then
  echo ""
  echo "缺少 .env 文件。"
  echo "请执行：cp .env.example .env，然后填写 DATABASE_URL。"
  exit 1
fi

if ! grep -q "^DATABASE_URL=postgresql://" .env; then
  echo ""
  echo ".env 中缺少有效的 DATABASE_URL=postgresql://..."
  exit 1
fi

echo ""
echo "==> 构建并启动容器"
$COMPOSE up -d --build

echo ""
echo "==> 容器状态"
$COMPOSE ps

FRONTEND_HOST_PORT=$($COMPOSE port frontend 80 2>/dev/null | tail -n 1 | sed 's/.*://')
BACKEND_HOST_PORT=$($COMPOSE port backend 8000 2>/dev/null | tail -n 1 | sed 's/.*://')

if [ -z "$FRONTEND_HOST_PORT" ]; then
  FRONTEND_HOST_PORT=$(grep "^FRONTEND_PORT=" .env 2>/dev/null | tail -n 1 | cut -d= -f2-)
fi
if [ -z "$BACKEND_HOST_PORT" ]; then
  BACKEND_HOST_PORT=$(grep "^BACKEND_PORT=" .env 2>/dev/null | tail -n 1 | cut -d= -f2-)
fi
FRONTEND_HOST_PORT=${FRONTEND_HOST_PORT:-80}
BACKEND_HOST_PORT=${BACKEND_HOST_PORT:-8000}

echo ""
echo "==> 健康检查"
if command -v curl >/dev/null 2>&1; then
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    HEALTH_RESPONSE=$(curl -fsS "http://127.0.0.1:${BACKEND_HOST_PORT}/api/health" 2>/dev/null || true)
    if echo "$HEALTH_RESPONSE" | grep -q '"db":true'; then
      echo "后端健康检查通过: http://127.0.0.1:${BACKEND_HOST_PORT}/api/health"
      break
    elif [ -n "$HEALTH_RESPONSE" ]; then
      echo "后端已响应，但数据库未就绪: $HEALTH_RESPONSE"
    fi
    sleep 2
  done
else
  echo "未安装 curl，跳过 HTTP 健康检查。"
fi

echo ""
echo "部署完成。"
if [ "$FRONTEND_HOST_PORT" = "80" ]; then
  echo "前端地址: http://服务器IP/"
else
  echo "前端地址: http://服务器IP:${FRONTEND_HOST_PORT}/"
fi
echo "后端健康检查: http://服务器IP:${BACKEND_HOST_PORT}/api/health"
echo "也可以通过前端 Nginx 代理访问后端: http://服务器IP:${FRONTEND_HOST_PORT}/api/health"
echo ""
echo "查看日志:"
echo "  $COMPOSE logs -f"
echo ""
echo "停止服务:"
echo "  $COMPOSE down"
