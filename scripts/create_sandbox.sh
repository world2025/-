#!/usr/bin/env bash
set -euo pipefail

SANDBOX_DIR="${1:-.sandbox}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[ERROR] Python not found: $PYTHON_BIN" >&2
  exit 1
fi

echo "[INFO] Creating sandbox virtual environment: $SANDBOX_DIR"
"$PYTHON_BIN" -m venv "$SANDBOX_DIR"

# shellcheck disable=SC1091
source "$SANDBOX_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel

echo "[INFO] Installing runtime dependencies"
python -m pip install -r requirements.txt

echo "[INFO] Installing test dependencies"
python -m pip install -r requirements-dev.txt

echo "[DONE] Sandbox ready"
echo "       source $SANDBOX_DIR/bin/activate"
echo "       uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
