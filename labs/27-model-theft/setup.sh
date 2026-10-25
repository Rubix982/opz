#!/usr/bin/env bash
# Makes the lab's virtualenv (Python 3.12 if you have it) with scikit-learn.
set -euo pipefail
cd "$(dirname "$0")"
PY=""
for p in python3.12 ~/.pyenv/versions/3.12*/bin/python3 python3.13 python3; do
  if "$p" -c 'import sys; assert sys.version_info >= (3, 10)' >/dev/null 2>&1; then PY=$p; break; fi
done
[ -n "$PY" ] || { echo "need Python 3.10+"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q -r requirements.txt
echo "Ready. source .venv/bin/activate, then: python app/server.py"
