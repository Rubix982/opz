#!/usr/bin/env bash
# Starts the model store (local S3 on localhost:9029) and the audit collector,
# runs infra/init.sh, and makes .venv with boto3. Re-run after changing infra/,
# config/ or compose.yaml.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p audit
docker compose up -d --force-recreate --remove-orphans
docker compose wait init >/dev/null 2>&1 || true
docker compose logs init | sed 's/^/  /'
echo "Up. Try: .venv/bin/python app/serve.py load sentiment/v3"
