#!/usr/bin/env bash
# Make a model version live: ./deploy.sh v1   (also how we roll back)
set -euo pipefail
cd "$(dirname "$0")"
[ -d "models/$1" ] || { echo "no such version: models/$1"; exit 1; }
python3 tools/copy_files.py "$1"
