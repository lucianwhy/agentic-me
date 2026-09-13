#!/usr/bin/env bash
# 本地 / 服务器非 Docker 启动：创建 venv、安装依赖、uvicorn --reload
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 ${PYTHON_BIN}，请安装 Python 3.11+"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "创建虚拟环境 .venv ..."
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已从 .env.example 创建 .env。没有 API Key 也可以先启动首页和 /health。"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "启动 ChatCV：http://${HOST}:${PORT}  （设置 OPENAI_API_KEY 后即可对话）"
exec uvicorn main:app --reload --host "$HOST" --port "$PORT"
