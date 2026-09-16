#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# 使用独立检查点库，验证过程中不读写业务案件。
check_dir="$(mktemp -d)"
CLAIMS_CHECKPOINT_DB="$check_dir/checkpoints.sqlite" .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8001 > "$check_dir/uvicorn.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
ready=false
for attempt in {1..30}; do
  if ! kill -0 "$server_pid" 2>/dev/null; then cat "$check_dir/uvicorn.log"; exit 1; fi
  if curl -fsS http://127.0.0.1:8001/health >/dev/null; then ready=true; break; fi
  sleep 1
done
if [[ "$ready" != true ]]; then cat "$check_dir/uvicorn.log"; exit 1; fi
.venv/bin/python health_check.py --url http://127.0.0.1:8001
SMOKE_BASE_URL=http://127.0.0.1:8001 .venv/bin/python -m pytest -q tests/test_smoke.py
