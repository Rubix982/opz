#!/usr/bin/env bash
# Starts the local AWS emulator (moto) on localhost:9033, makes the lab's
# virtualenv, and seeds the account. Re-run to reset everything.
set -euo pipefail
cd "$(dirname "$0")"
docker rm -f opz-lab33-moto >/dev/null 2>&1 || true
docker run -d --name opz-lab33-moto -e MOTO_EC2_LOAD_DEFAULT_AMIS=false -p 9033:5000 motoserver/moto:5.1.4 >/dev/null
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
for _ in $(seq 1 40); do curl -s localhost:9033 >/dev/null && break; sleep 0.5; done
.venv/bin/python app/seed.py
echo "Ready. source .venv/bin/activate, then see the README."
