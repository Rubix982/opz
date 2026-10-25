#!/usr/bin/env bash
# Starts its own copy of the stack from your compose.yaml and infra/ (project
# opz-lab30-check, S3 on port 19030) and the app on 18030 with 4-second share
# links. Passes only when anonymous listing and downloads are refused, the app
# still stores and reads exports, and a partner link works and then expires.
set -u
cd "$(dirname "$0")"
export COMPOSE_PROJECT_NAME=opz-lab30-check S3_PORT=19030
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (it makes .venv)"; exit 1; }
S3=http://127.0.0.1:$S3_PORT
BUCKET=acme-customer-exports
TTL=4
fail=0

cleanup() { kill "${app:-}" 2>/dev/null; wait "${app:-}" 2>/dev/null; docker compose down -v --remove-orphans >/dev/null 2>&1; }
trap cleanup EXIT

docker compose up -d --force-recreate >.check.log 2>&1 || { echo "compose up failed, see .check.log"; exit 1; }
docker compose wait init >>.check.log 2>&1
[ "$(docker compose ps -a --format '{{.ExitCode}}' init)" = 0 ] || { echo "infra/init.sh failed, see: docker compose -p $COMPOSE_PROJECT_NAME logs init"; docker compose logs init >>.check.log; exit 1; }

S3_ENDPOINT=$S3 SHARE_TTL_SECONDS=$TTL PORT=18030 $PY app/exports.py >>.check.log 2>&1 & app=$!
for _ in $(seq 1 40); do curl -s -o /dev/null localhost:18030/exports/x && break; sleep 0.25; done

code() { curl -s -o /dev/null -w '%{http_code}' "$1"; }

c=$(code "$S3/$BUCKET/")
if [ "$c" = 403 ]; then echo "pass  anonymous list refused (403)"
else echo "FAIL  anonymous list of the bucket got $c"; fail=1; fi

c=$(code "$S3/$BUCKET/2026/q1-export.csv")
if [ "$c" = 403 ]; then echo "pass  anonymous download refused (403)"
else echo "FAIL  anonymous download of a customer export got $c"; fail=1; fi

body="customer_id,name\n9001,Check $(date +%s)"
curl -s -o /dev/null -X POST --data-binary "$(printf "$body")" localhost:18030/exports/check-export
got=$(curl -s localhost:18030/exports/check-export)
if [ "$got" = "$(printf "$body")" ]; then echo "pass  app still stores and reads exports"
else echo "FAIL  app couldn't store/read an export (got: ${got:0:80})"; fail=1; fi

url=$(curl -s localhost:18030/exports/check-export/share | $PY -c "import json,sys; print(json.load(sys.stdin)['url'])" 2>/dev/null)
got=$(curl -s "$url")
if [ -n "$url" ] && [ "$got" = "$(printf "$body")" ]; then echo "pass  partner link works"
else echo "FAIL  partner link doesn't return the export (${url:-no url})"; fail=1; fi

sleep $((TTL + 2))
c=$(code "$url")
if [ "$c" = 403 ]; then echo "pass  partner link expired after SHARE_TTL_SECONDS"
else echo "FAIL  partner link still answers $c after ${TTL}s + 2s (SHARE_TTL_SECONDS=$TTL)"; fail=1; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
