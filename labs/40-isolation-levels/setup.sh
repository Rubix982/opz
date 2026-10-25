#!/usr/bin/env bash
# Starts Postgres and the clinic API on localhost:8040. Re-run after editing app/.
set -euo pipefail
cd "$(dirname "$0")"
docker compose up -d --build --wait
curl -fs -XPOST "localhost:8040/reset?seats=5" >/dev/null
echo "Up. Try: python3 tools/race.py book   and   python3 tools/race.py off-call"
