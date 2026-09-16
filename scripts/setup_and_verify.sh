#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# 可用PYTHON_BIN=python3.10覆盖；本机默认采用干净的Python 3.12发行版。
"${PYTHON_BIN:-python3.12}" -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
if [[ ! -f .env ]]; then cp .env.example .env; chmod 600 .env; fi
python -m pytest -q
bash scripts/verify.sh
