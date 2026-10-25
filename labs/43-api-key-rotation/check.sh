#!/usr/bin/env bash
# Runs a fresh emulator (port 9143) and gateway (port 18043), keeps all three
# clients calling the API, and rotates keys with app/rotate.py twice:
#   1. "billing", with every client re-reading its key: zero requests may be
#      refused, the client must end up on a new key, and the old key must stop
#      working.
#   2. "reports", while one copy of the reports client keeps using the old key:
#      the rotation must refuse to finish (nonzero exit) and leave the old key
#      working, because something still depends on it.
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (makes .venv)"; exit 1; }
export AWS_ENDPOINT_URL=http://localhost:9143 GATEWAY_URL=http://127.0.0.1:18043 CACHE_TTL=3
export KEYS_DIR="$PWD/.check-keys" ROTATE_DRAIN_TIMEOUT=10
L1=$(mktemp); L2=$(mktemp)
fail=0; gw=""; cl=""

docker rm -f opz-lab43-check >/dev/null 2>&1
docker run -d --name opz-lab43-check -p 9143:5000 motoserver/moto:5.1.4 >/dev/null
trap 'kill $gw $cl 2>/dev/null; wait $gw $cl 2>/dev/null; docker rm -f opz-lab43-check >/dev/null 2>&1; rm -rf "$KEYS_DIR" "$L1" "$L2"' EXIT
for _ in $(seq 1 40); do curl -s localhost:9143 >/dev/null && break; sleep 0.5; done
rm -rf "$KEYS_DIR"
$PY infra/seed.py >.check.log 2>&1 || { echo "FAIL  infra/seed.py crashed; see .check.log"; exit 1; }
(cd app && PORT=18043 exec ../$PY gateway.py) >>.check.log 2>&1 & gw=$!
for _ in $(seq 1 40); do curl -s "$GATEWAY_URL/stats" >/dev/null && break; sleep 0.25; done

with_timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }
status_with() { curl -s -o /dev/null -w '%{http_code}' -H "x-api-key: $1" "$GATEWAY_URL/orders"; }
denied() { awk -F'\t' -v who="${2:-}" '($2 == who || who == "") && $3 != 200 {n++} END {print n+0}' "$1"; }

# --- 1. a normal rotation ------------------------------------------------------
$PY app/clients.py --quiet --ledger "$L1" >>.check.log 2>&1 & cl=$!
sleep 2
if [ "$(denied "$L1")" = 0 ] && [ -s "$L1" ]; then echo "pass  traffic healthy before the rotation"
else echo "FAIL  clients failing before any rotation; see .check.log"; fail=1; fi

old_billing=$(cat "$KEYS_DIR/billing.key")
with_timeout 60 $PY app/rotate.py billing >>.check.log 2>&1; rc=$?
sleep 2; kill $cl 2>/dev/null; wait $cl 2>/dev/null; cl=""

n=$(denied "$L1")
if [ "$n" = 0 ]; then echo "pass  rotating billing: no client request refused"
else echo "FAIL  rotating billing: $n client requests refused ($(denied "$L1" billing) of them billing's)"; fail=1; fi

if [ "$rc" = 0 ]; then echo "pass  rotate.py billing reported success"
else echo "FAIL  rotate.py billing exited $rc"; fail=1; fi

new_billing=$(cat "$KEYS_DIR/billing.key")
if [ "$new_billing" != "$old_billing" ] && [ "$(status_with "$new_billing")" = 200 ]; then
  echo "pass  billing was handed a new key, and it works"
else echo "FAIL  billing's key file still holds the old key (nobody handed the client its new one)"; fail=1; fi

sleep 4  # longer than the gateway's key cache
if [ "$(status_with "$old_billing")" = 403 ]; then echo "pass  old billing key refused after the rotation"
else echo "FAIL  old billing key still works after the rotation finished"; fail=1; fi

# --- 2. a rotation while someone still uses the old key ------------------------
$PY app/clients.py --quiet --sticky reports --ledger "$L2" >>.check.log 2>&1 & cl=$!
sleep 2
old_reports=$(cat "$KEYS_DIR/reports.key")
with_timeout 60 $PY app/rotate.py reports >>.check.log 2>&1; rc=$?
sleep 4
code_after=$(status_with "$old_reports")
kill $cl 2>/dev/null; wait $cl 2>/dev/null; cl=""

if [ "$rc" != 0 ]; then echo "pass  rotate.py refused to finish while the old reports key was still in use"
else echo "FAIL  rotate.py reports finished (exit 0) while a client was still using the old key"; fail=1; fi

if [ "$code_after" = 200 ]; then echo "pass  old reports key left working for the client still on it"
else echo "FAIL  old reports key was cut off (HTTP $code_after) under a client still using it"; fail=1; fi

n=$(denied "$L2" reports)
if [ "$n" = 0 ]; then echo "pass  the client stuck on the old key was never locked out"
else echo "FAIL  the client stuck on the old key had $n requests refused"; fail=1; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
