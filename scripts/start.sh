#!/usr/bin/env bash
# OpenCR — local dev launcher.
#
# Defaults to the `local` backend if MODEL_BACKEND is unset and no
# vLLM-style remote URL is reachable, so `./scripts/start.sh` from a
# fresh clone Just Works on a Mac.
#
# Override anything via env vars:
#   MODEL_BACKEND=local|remote|vllm
#   MODEL_SERVER_URL=https://your-endpoint
#   MODEL_API_KEY=sk-...
#   INPUT_DIR=./input  OUTPUT_DIR=./output
#   PORT=39672

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${MODEL_BACKEND:-}" ]]; then
  if [[ -n "${MODEL_SERVER_URL:-}" ]]; then
    export MODEL_BACKEND=remote
  else
    export MODEL_BACKEND=local
  fi
fi

export INPUT_DIR="${INPUT_DIR:-$(pwd)/input}"
export OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/output}"
mkdir -p "$INPUT_DIR" "$OUTPUT_DIR"

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
PORT="${PORT:-39672}"
HOST="${HOST:-0.0.0.0}"

echo "→ OpenCR  backend=$MODEL_BACKEND  http://$HOST:$PORT"
echo "  input=$INPUT_DIR"
echo "  output=$OUTPUT_DIR"

exec python3 -m uvicorn ocr_pipeline.main:app --host "$HOST" --port "$PORT" "$@"
