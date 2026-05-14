#!/usr/bin/env bash
# OpenCR — GPU-first dev launcher.
#
# Defaults to a remote/OpenAI-compatible vLLM endpoint on localhost. For the
# full GPU stack, prefer `docker compose up -d`.
#
# Override anything via env vars:
#   MODEL_BACKEND=remote|vllm
#   MODEL_SERVER_URL=http://localhost:39671
#   MODEL_API_KEY=sk-...
#   INPUT_DIR=./input  OUTPUT_DIR=./output
#   PORT=39672

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${MODEL_BACKEND:-}" ]]; then
  export MODEL_BACKEND=remote
fi
export MODEL_SERVER_URL="${MODEL_SERVER_URL:-http://localhost:39671}"

export INPUT_DIR="${INPUT_DIR:-$(pwd)/input}"
export OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/output}"
mkdir -p "$INPUT_DIR" "$OUTPUT_DIR"

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
PORT="${PORT:-39672}"
HOST="${HOST:-0.0.0.0}"
if [[ -z "${PYTHON_BIN:-}" && -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

echo "→ OpenCR  backend=$MODEL_BACKEND  http://$HOST:$PORT"
echo "  input=$INPUT_DIR"
echo "  output=$OUTPUT_DIR"
echo "  python=$PYTHON_BIN"

UVICORN_ARGS=()
if [[ "${ACCESS_LOG:-0}" != "1" ]]; then
  UVICORN_ARGS+=(--no-access-log)
fi

exec "$PYTHON_BIN" -m uvicorn ocr_pipeline.main:app --host "$HOST" --port "$PORT" "${UVICORN_ARGS[@]}" "$@"
