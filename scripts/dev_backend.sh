#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}/backend"

if [ -n "${PYTHON:-}" ] && command -v "${PYTHON}" >/dev/null 2>&1; then
  PY="${PYTHON}"
elif command -v python3.12 >/dev/null 2>&1; then
  PY="python3.12"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "python3 not found." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  "${PY}" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

exec python -m uvicorn app.main:app --reload --host "${HOST:-0.0.0.0}" --port "${PORT:-8080}"

