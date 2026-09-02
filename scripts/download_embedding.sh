#!/usr/bin/env bash
# Download local embedding model without requiring `pip install -e`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

# Mainland China: huggingface.co is often unreachable; hf-mirror works with XET disabled.
if [ -z "${HF_ENDPOINT:-}" ]; then
  export HF_ENDPOINT="https://hf-mirror.com"
  export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
fi

exec python -m traceforge.memory.download_embedding "$@"
