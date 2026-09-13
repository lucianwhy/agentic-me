#!/usr/bin/env bash
# 用简历 PDF + data/about_me.md 构建向量库。需要已配置 OPENAI_API_KEY（或兼容接口）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [ ! -f .env ]; then
  echo "缺少 .env，请先复制 .env.example 并填写 OPENAI_API_KEY"
  exit 1
fi

python -m app.modules.rag_pipeline --ingest
