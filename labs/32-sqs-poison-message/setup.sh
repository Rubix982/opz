#!/usr/bin/env bash
# Starts the local AWS emulator (moto) on localhost:9032, makes the lab's
# virtualenv, and creates the queues with infra/queues.py.
set -euo pipefail
cd "$(dirname "$0")"
docker rm -f opz-lab32-moto >/dev/null 2>&1 || true
docker run -d --name opz-lab32-moto -p 9032:5000 motoserver/moto:5.1.4 >/dev/null
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
for _ in $(seq 1 40); do curl -s localhost:9032 >/dev/null && break; sleep 0.5; done
.venv/bin/python infra/queues.py
echo "Ready. source .venv/bin/activate, then see the README."
