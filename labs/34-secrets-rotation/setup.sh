#!/usr/bin/env bash
# Starts the local AWS emulator (moto) on localhost:9034, makes the lab's
# virtualenv, and creates the secret. The database you start yourself (README).
set -euo pipefail
cd "$(dirname "$0")"
docker rm -f opz-lab34-moto >/dev/null 2>&1 || true
docker run -d --name opz-lab34-moto -p 9034:5000 motoserver/moto:5.1.4 >/dev/null
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
for _ in $(seq 1 40); do curl -s localhost:9034 >/dev/null && break; sleep 0.5; done
.venv/bin/python tools/seed.py
echo "Ready. Start the database: python3 db/server.py   (restart it whenever you re-run setup)"
