#!/usr/bin/env bash
# Runs its own emulator (port 9134) and database (port 18034), then rotates the
# secret four times with app/rotate.py:
#   1. healthy           must succeed; the new secret logs in, and an app still
#                        holding the old password keeps working (overlap)
#   2. DB unreachable    must FAIL LOUDLY (nonzero exit); apps keep working
#   3. change ignored    must FAIL LOUDLY; apps keep working
#   4. healthy again     must recover and succeed
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (makes .venv)"; exit 1; }
export AWS_ENDPOINT_URL=http://localhost:9134 DB_URL=http://localhost:18034
fail=0

docker rm -f opz-lab34-check >/dev/null 2>&1
docker run -d --name opz-lab34-check -p 9134:5000 motoserver/moto:5.1.4 >/dev/null
PORT=18034 python3 db/server.py >.check-db.log 2>&1 & db=$!
trap 'kill $db 2>/dev/null; wait $db 2>/dev/null; docker rm -f opz-lab34-check >/dev/null 2>&1' EXIT
for _ in $(seq 1 40); do curl -s localhost:9134 >/dev/null && break; sleep 0.5; done
for _ in $(seq 1 20); do curl -s -o /dev/null localhost:18034/login -d '{}' && break; sleep 0.2; done
$PY tools/seed.py >.check.log 2>&1 || { echo "FAIL  couldn't create the secret; see .check.log"; exit 1; }

current() { $PY -c "
import json, sys; sys.path.insert(0, 'app')
from common import SECRET_ID, secrets
print(json.loads(secrets().get_secret_value(SecretId=SECRET_ID, VersionStage='AWSCURRENT')['SecretString'])['password'])"; }
login() { $PY -c "
import sys; sys.path.insert(0, 'app')
from common import can_login
sys.exit(0 if can_login(sys.argv[1]) else 1)" "$1"; }
fault() { curl -s -XPOST localhost:18034/admin/fault -d "{\"mode\": \"$1\"}" >/dev/null; }
ok()  { echo "pass  $1"; }
bad() { echo "FAIL  $1"; fail=1; }

round() {  # label, fault, expect (succeed|fail)
  local label=$1 mode=$2 expect=$3
  echo "      --- rotation $label"
  fault "$mode"
  local held; held=$(current)              # an app instance fetched this before the rotation
  $PY app/rotate.py >>.check.log 2>&1; local rc=$?
  fault none
  if [ "$expect" = succeed ]; then
    [ $rc = 0 ] && ok "rotation reported success" || bad "rotation exited $rc on a healthy system"
    [ "$(current)" != "$held" ] && ok "secret actually changed" || bad "AWSCURRENT still holds the old password"
    login "$held" && ok "an app still holding the previous password keeps working" \
                  || bad "the previous password stopped working at once; every app that cached it just broke"
  else
    [ $rc != 0 ] && ok "failed rotation exited nonzero (someone gets told)" \
                 || bad "rotation failed but exited 0: a silent failure"
  fi
  login "$(current)" && ok "AWSCURRENT logs in" || bad "AWSCURRENT does NOT log in: the app is down"
  $PY app/app.py >>.check.log 2>&1 && ok "app connects" || bad "app can't connect"
}

round "1 (healthy)" none succeed
round "2 (database unreachable)" down fail
round "3 (change silently ignored)" ignore fail
round "4 (healthy again: recovers)" none succeed

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
