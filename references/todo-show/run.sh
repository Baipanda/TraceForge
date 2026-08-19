#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_ROOT"

echo "Todo Show 一键启动"
echo "项目目录: $PROJECT_ROOT"

install_backend_deps() {
  echo "后端依赖缺失，正在安装到 .venv..."

  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
  unset PIP_PROXY pip_proxy REQUESTS_CA_BUNDLE CURL_CA_BUNDLE SSL_CERT_FILE
  export NO_PROXY="*"
  export no_proxy="*"

  PIP_CONFIG_FILE=/dev/null "$PYTHON" -m pip install -r backend/requirements.txt \
    --proxy "" \
    --index-url https://pypi.org/simple && return 0

  echo ""
  echo "官方 PyPI 安装失败，尝试阿里云镜像..."
  PIP_CONFIG_FILE=/dev/null "$PYTHON" -m pip install -r backend/requirements.txt \
    --proxy "" \
    --index-url https://mirrors.aliyun.com/pypi/simple && return 0

  echo ""
  echo "阿里云镜像安装失败，尝试清华 HTTP 镜像..."
  PIP_CONFIG_FILE=/dev/null "$PYTHON" -m pip install -r backend/requirements.txt \
    --proxy "" \
    --index-url http://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn && return 0

  echo ""
  echo "后端依赖安装失败。请检查网络或手动执行："
  echo "  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY"
  echo "  PIP_CONFIG_FILE=/dev/null $PYTHON -m pip install -r backend/requirements.txt --proxy \"\" --index-url https://pypi.org/simple"
  return 1
}

free_port() {
  port="$1"
  pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti "tcp:$port" 2>/dev/null || true)
  elif command -v fuser >/dev/null 2>&1; then
    pids=$(fuser "$port/tcp" 2>/dev/null || true)
  elif command -v netstat >/dev/null 2>&1 && command -v taskkill >/dev/null 2>&1; then
    pids=$(netstat -ano 2>/dev/null | awk -v port=":$port" '$0 ~ port && $0 ~ /LISTENING/ { print $NF }' | sort -u)
  fi

  if [ -n "$pids" ]; then
    echo "端口 $port 已被占用，正在停止旧进程: $pids"
    for pid in $pids; do
      if command -v taskkill >/dev/null 2>&1; then
        taskkill //PID "$pid" //F >/dev/null 2>&1 || kill "$pid" 2>/dev/null || true
      else
        kill "$pid" 2>/dev/null || true
      fi
    done
    sleep 1
  fi
}

check_backend_health() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS http://localhost:8000/api/health >/dev/null 2>&1
  else
    "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=2).read()" >/dev/null 2>&1
  fi
}

if [ ! -f ".env" ]; then
  echo ""
  echo "缺少 .env 文件，后端无法读取 DATABASE_URL。"
  echo "请在项目根目录创建 .env，并设置 DATABASE_URL=postgresql://..."
  exit 1
fi

PYTHON=""
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
elif [ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
  PYTHON="$PROJECT_ROOT/.venv/Scripts/python.exe"
fi

if [ -n "$PYTHON" ] && ! "$PYTHON" -c "import sys; exit(0 if (3, 9) <= sys.version_info < (3, 14) else 1)" >/dev/null 2>&1; then
  PYTHON=""
fi

if ! command -v npm >/dev/null 2>&1; then
  echo ""
  echo "未找到 npm 命令。请先安装 Node.js。"
  exit 1
fi

echo ""
echo "==> 检查后端依赖"
if [ -z "$PYTHON" ]; then
  SYSTEM_PYTHON=""
  for candidate in "python3.13" "python3.12" "python3.11" "python3.10" "python3.9" "python3" "python"; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys; exit(0 if (3, 9) <= sys.version_info < (3, 14) else 1)" >/dev/null 2>&1; then
      SYSTEM_PYTHON="$candidate"
      break
    fi
  done

  if [ -z "$SYSTEM_PYTHON" ] && command -v py >/dev/null 2>&1; then
    for version in "3.13" "3.12" "3.11" "3.10" "3.9"; do
      if py "-$version" -c "import sys" >/dev/null 2>&1; then
        SYSTEM_PYTHON="py -$version"
        break
      fi
    done
  fi

  if [ -z "$SYSTEM_PYTHON" ]; then
    echo ""
    echo "现有虚拟环境不可用，且未找到 Python 3.9-3.13。"
    exit 1
  fi

  echo "创建 Python 虚拟环境..."
  rm -rf .venv
  $SYSTEM_PYTHON -m venv .venv
  if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
  elif [ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON="$PROJECT_ROOT/.venv/Scripts/python.exe"
  else
    echo "未找到虚拟环境 Python，请检查 venv 创建是否成功。"
    exit 1
  fi
else
  echo "使用现有虚拟环境: $PYTHON"
fi

if ! $PYTHON -c "import fastapi, uvicorn, psycopg2, dotenv" >/dev/null 2>&1; then
  install_backend_deps
fi

echo ""
echo "==> 检查前端依赖"
if [ ! -d "frontend/node_modules" ]; then
  (cd frontend && npm install)
fi

echo ""
echo "==> 应用数据库迁移"
$PYTHON backend/apply_migrations.py

echo ""
echo "==> 检查并释放端口"
free_port 8000
free_port 3000

echo ""
echo "==> 启动后端: http://localhost:8000"
(cd backend && $PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!

echo "==> 等待后端就绪"
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if check_backend_health; then
    ready=1
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "后端启动失败，请查看上方 uvicorn 错误。"
    exit 1
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "后端未在预期时间内就绪，请检查数据库连接或端口占用。"
  exit 1
fi

echo "==> 启动前端: http://localhost:3000"
(cd frontend && npm run dev -- --host 0.0.0.0) &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "正在停止服务..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo ""
echo "启动完成。按 Ctrl+C 停止。"
echo "前端地址: http://localhost:3000"
echo "后端健康检查: http://localhost:8000/api/health"

wait
