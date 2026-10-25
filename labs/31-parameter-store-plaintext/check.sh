#!/usr/bin/env bash
# Builds its own copy of the stack (project opz-lab31-check, emulator on 19031,
# app on 18031), runs your infra/bootstrap.py and starts your app. Passes only
# when the two secrets are SecureStrings under the team's own KMS key, a
# read-only look at Parameter Store doesn't show them, the app still gets the
# right values, and neither value appears anywhere it shouldn't: the
# bootstrap's output, docker inspect, compose config, the app's logs, or any
# file in this folder (other than infra/seed.json, which stands in for the
# person who typed them in).
set -u
cd "$(dirname "$0")"
export COMPOSE_PROJECT_NAME=opz-lab31-check AWS_PORT=19031 APP_PORT=18031
export AWS_ENDPOINT_URL=http://127.0.0.1:19031 AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (it makes .venv)"; exit 1; }
fail=0

[ -f .env.app ] && cp .env.app .env.app.check-backup
cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1
  if [ -f .env.app.check-backup ]; then mv .env.app.check-backup .env.app; else rm -f .env.app; fi
}
trap cleanup EXIT

secrets=$($PY -c "
import json; d = json.load(open('infra/seed.json'))
print('\n'.join(v for k, v in d.items() if k.endswith(('db_password', 'payment_api_key'))))")

docker compose up -d --force-recreate --wait aws >.check.log 2>&1 || { echo "emulator didn't start, see .check.log"; exit 1; }
boot=$($PY infra/bootstrap.py 2>&1) || { echo "FAIL  infra/bootstrap.py failed:"; echo "$boot" | sed 's/^/        /'; exit 1; }
docker compose up -d --build --force-recreate app >>.check.log 2>&1 || { echo "app didn't build/start, see .check.log"; exit 1; }
for _ in $(seq 1 40); do curl -fs localhost:$APP_PORT/status >/dev/null 2>&1 && break; sleep 0.5; done

# 1-2. How the secrets are stored, and what a read-only look shows.
$PY - <<'PY' || fail=1
import json, boto3
ssm = boto3.client("ssm")
seed = json.load(open("infra/seed.json"))
names = [k for k in seed if k.endswith(("db_password", "payment_api_key"))]
described = {p["Name"]: p for p in ssm.describe_parameters()["Parameters"]}
ok = True
for name in names:
    p = described.get(name)
    if p is None:
        print(f"FAIL  {name} isn't in Parameter Store"); ok = False; continue
    if p["Type"] != "SecureString":
        print(f"FAIL  {name} is a plain {p['Type']}"); ok = False
    elif p.get("KeyId") in (None, "alias/aws/ssm"):
        print(f"FAIL  {name} uses the AWS-managed default key, not the team's own KMS key"); ok = False
    else:
        print(f"pass  {name} is a SecureString under {p['KeyId']}")
peek = {p["Name"]: p["Value"] for p in ssm.get_parameters_by_path(Path="/orders", Recursive=True, WithDecryption=False)["Parameters"]}
shown = [n for n in names if peek.get(n) == seed[n]]
if shown: print(f"FAIL  a read without decryption shows the value of: {', '.join(shown)}"); ok = False
else: print("pass  a read without decryption doesn't show the secrets")
raise SystemExit(0 if ok else 1)
PY

# 3. The app still works with the right values.
status=$(curl -fs localhost:$APP_PORT/status 2>/dev/null)
$PY - "$status" <<'PY' || fail=1
import hashlib, json, sys
seed = json.load(open("infra/seed.json"))
fp = lambda v: hashlib.sha256(v.encode()).hexdigest()[:12]
try: s = json.loads(sys.argv[1])
except Exception: print("FAIL  app isn't answering /status (docker compose -p opz-lab31-check logs app)"); sys.exit(1)
want = (fp(seed["/orders/prod/db_password"]), fp(seed["/orders/prod/payment_api_key"]))
if (s.get("db_password_fingerprint"), s.get("payment_api_key_fingerprint")) == want: print("pass  app loaded the right secrets")
else: print(f"FAIL  app's secrets don't match Parameter Store: {s}"); sys.exit(1)
PY

# 4. Nowhere it shouldn't be.
cid=$(docker compose ps -q app)
leaks() {  # label, text
  local found=""
  while IFS= read -r s; do [ -n "$s" ] && [[ "$2" == *"$s"* ]] && found=yes; done <<< "$secrets"
  if [ -n "$found" ]; then echo "FAIL  a secret appears in $1"; fail=1; else echo "pass  no secret in $1"; fi
}
leaks "bootstrap output" "$boot"
leaks "docker inspect" "$(docker inspect "$cid" 2>/dev/null)"
leaks "docker compose config" "$(docker compose config 2>/dev/null)"
leaks "the app's logs" "$(docker compose logs app 2>/dev/null)"
files=$(grep -rlF -f <(echo "$secrets") . --exclude-dir=.venv --exclude-dir=.git --exclude=seed.json --exclude=.check.log --exclude=.env.app.check-backup 2>/dev/null)
if [ -n "$files" ]; then echo "FAIL  a secret is written to: $(echo $files)"; fail=1
else echo "pass  no secret written to any file here"; fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
