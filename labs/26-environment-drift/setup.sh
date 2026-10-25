#!/usr/bin/env bash
# Builds the lab's package index and the researcher's laptop environment
# (.venv-laptop, installed back on 2026-09-20). Works offline.
set -euo pipefail
cd "$(dirname "$0")"
python3 tools/make_index.py
rm -rf .venv-laptop
python3 -m venv .venv-laptop
.venv-laptop/bin/pip install -q --no-index --find-links index/2026-09-20 -r app/requirements.txt
echo "Laptop:     .venv-laptop/bin/python app/train.py"
echo "Production: docker build -f app/Dockerfile -t opz-lab26 . && docker run --rm opz-lab26"
