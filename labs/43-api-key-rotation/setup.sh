#!/usr/bin/env bash
# Starts the local AWS emulator (moto) on localhost:9043, makes the lab's
# virtualenv, and creates the API, usage plan and keys with infra/seed.py.
set -euo pipefail
cd "$(dirname "$0")"
docker rm -f opz-lab43-moto >/dev/null 2>&1 || true
docker run -d --name opz-lab43-moto -p 9043:5000 motoserver/moto:5.1.4 >/dev/null
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
for _ in $(seq 1 40); do curl -s localhost:9043 >/dev/null && break; sleep 0.5; done
rm -rf keys
.venv/bin/python infra/seed.py
echo "Ready. source .venv/bin/activate, then see the README."
