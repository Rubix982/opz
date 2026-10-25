#!/usr/bin/env bash
# Starts the local AWS emulator, runs infra/bootstrap.py against it, then starts
# the app. Re-run after changing infra/, app/ or compose.yaml. (The emulator
# keeps everything in memory, so each run starts from empty.)
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
docker compose up -d --force-recreate --wait aws
AWS_ENDPOINT_URL=http://127.0.0.1:${AWS_PORT:-9031} .venv/bin/python infra/bootstrap.py
docker compose up -d --build --force-recreate app
sleep 2
echo "Up. Try: curl -s localhost:8031/status   and   docker compose logs app"
