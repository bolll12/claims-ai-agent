#!/usr/bin/env bash
# macOS/Linux bash：创建 venv、安装依赖、执行两条验证链路。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -c 'import sys; assert sys.version_info >= (3, 10), "需要 Python 3.10+"; print(sys.version)'
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python -m pytest -q
bash scripts/verify.sh
