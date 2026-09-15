#!/usr/bin/env bash
# 在已安装依赖的虚拟环境中启动 8001 端口并执行真实 HTTP 验证。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
SMOKE_DIR="$(mktemp -d)"
UVICORN_PID=""
cleanup() {
    if [[ -n "$UVICORN_PID" ]]; then
        kill "$UVICORN_PID" 2>/dev/null || true
        wait "$UVICORN_PID" 2>/dev/null || true
    fi
    echo "服务日志：$SMOKE_DIR/uvicorn.log"
}
trap cleanup EXIT

python - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 8001))
print("端口 8001 可用")
PY

python -m uvicorn app:app --host 127.0.0.1 --port 8001 > "$SMOKE_DIR/uvicorn.log" 2>&1 &
UVICORN_PID=$!
READY=0
for ((attempt = 1; attempt <= 30; attempt++)); do
    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        cat "$SMOKE_DIR/uvicorn.log"
        exit 1
    fi
    if curl --noproxy '*' --silent --fail --max-time 1 http://127.0.0.1:8001/health > "$SMOKE_DIR/health.json"; then
        READY=1
        break
    fi
    sleep 1
done
if [[ "$READY" -ne 1 ]]; then
    cat "$SMOKE_DIR/uvicorn.log"
    exit 1
fi
python - "$SMOKE_DIR/health.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as file:
    result = json.load(file)
assert result == {"status": "ok"}, result
print("健康检查通过：", result)
PY
SMOKE_BASE_URL=http://127.0.0.1:8001 python -m pytest -q tests/test_smoke.py
