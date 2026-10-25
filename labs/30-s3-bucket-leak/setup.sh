#!/usr/bin/env bash
# Starts the local S3 (MinIO) and applies infra/init.sh, and makes .venv with
# boto3 for the app. Re-run after any change to infra/ or compose.yaml.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
docker compose up -d --force-recreate --remove-orphans
docker compose wait init >/dev/null 2>&1 || true
docker compose logs init | sed 's/^/  /'
echo "Up. S3 on localhost:9030. Run the app: .venv/bin/python app/exports.py"
