#!/usr/bin/env bash
# Starts its own copy of the stack from your compose.yaml, infra/ and config/
# (project opz-lab29-check, S3 on port 19029, a temporary audit folder), then:
#   publishes a model as the trainer, reads it as the server, tries to read it
#   anonymously, tries to overwrite and delete it as the server, overwrites it
#   as the trainer and looks for the old version, tampers with it as the admin
#   and checks the server refuses it, and looks for the server's read in the audit log.
set -u
cd "$(dirname "$0")"
export COMPOSE_PROJECT_NAME=opz-lab29-check S3_PORT=19029
export S3_ENDPOINT=http://127.0.0.1:19029
export AUDIT_DIR; AUDIT_DIR=$(mktemp -d)
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (it makes .venv)"; exit 1; }
WORK=$(mktemp -d)
NAME=check-model/v1
fail=0

[ -f registry.json ] && cp registry.json registry.json.check-backup
cleanup() {
  docker compose down -v --remove-orphans >/dev/null 2>&1
  rm -rf "$WORK" "$AUDIT_DIR"
  # put registry.json back exactly as it was before the check
  if [ -f registry.json.check-backup ]; then mv registry.json.check-backup registry.json; else rm -f registry.json; fi
}
trap cleanup EXIT

docker compose up -d --force-recreate >.check.log 2>&1 || { echo "compose up failed, see .check.log"; exit 1; }
docker compose wait init >>.check.log 2>&1
if [ "$(docker compose ps -a --format '{{.ExitCode}}' init)" != 0 ]; then
  docker compose logs init >>.check.log; echo "infra/init.sh failed, see .check.log"; exit 1
fi

head -c 200000 /dev/urandom > "$WORK/a.bin"
head -c 200000 /dev/urandom > "$WORK/b.bin"
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }

# 1. the trainer can still publish
if $PY app/train.py publish "$NAME" "$WORK/a.bin" >>.check.log 2>&1; then echo "pass  trainer can publish a model"
else echo "FAIL  trainer couldn't publish (see .check.log)"; fail=1; fi

# 2. nobody without credentials can read
c=$(curl -s -o /dev/null -w '%{http_code}' "$S3_ENDPOINT/models/$NAME/model.bin")
if [ "$c" = 403 ]; then echo "pass  anonymous download refused (403)"
else echo "FAIL  anonymous download got $c"; fail=1; fi

# 3. the server can read
out=$($PY app/serve.py load "$NAME" 2>>.check.log)
if [[ $out == *"$(sha "$WORK/a.bin")"* ]]; then echo "pass  server loads the model it was given"
else echo "FAIL  server couldn't load the model (${out:-no output})"; fail=1; fi

# 4. the server's credentials can't change anything
$PY - "$NAME" <<'PY' || fail=1
import sys
sys.path.insert(0, "app")
from botocore.exceptions import ClientError
from common import BUCKET, client, model_key
s3, key, ok = client("server"), model_key(sys.argv[1]), True
for what, call in [("overwrite", lambda: s3.put_object(Bucket=BUCKET, Key=key, Body=b"evil")),
                   ("delete", lambda: s3.delete_object(Bucket=BUCKET, Key=key))]:
    try:
        call(); print(f"FAIL  server credentials can {what} models"); ok = False
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDenied": print(f"pass  server credentials can't {what} models")
        else: print(f"FAIL  server {what} failed oddly: {code}"); ok = False
sys.exit(0 if ok else 1)
PY

# 5. an overwrite is recoverable
$PY app/train.py publish "$NAME" "$WORK/b.bin" >>.check.log 2>&1
$PY - "$NAME" "$(sha "$WORK/a.bin")" <<'PY' || fail=1
import hashlib, sys
sys.path.insert(0, "app")
import boto3
from botocore.config import Config
from common import BUCKET, ENDPOINT, LAB, model_key, read_env_file
root = read_env_file(LAB / ".env")
s3 = boto3.client("s3", endpoint_url=ENDPOINT, aws_access_key_id=root["MINIO_ROOT_USER"],
                  aws_secret_access_key=root["MINIO_ROOT_PASSWORD"], region_name="us-east-1",
                  config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
key = model_key(sys.argv[1])
versions = s3.list_object_versions(Bucket=BUCKET, Prefix=key).get("Versions", [])
old = [v for v in versions if v["Key"] == key and not v["IsLatest"]]
found = any(hashlib.sha256(s3.get_object(Bucket=BUCKET, Key=key, VersionId=v["VersionId"])["Body"].read()).hexdigest() == sys.argv[2] for v in old)
if found: print("pass  overwritten model recoverable from its previous version")
else: print(f"FAIL  overwritten model is gone ({len(versions)} version(s) kept)"); sys.exit(1)
PY

# 6. a tampered artifact is refused
$PY - "$NAME" <<'PY'
import os, sys
sys.path.insert(0, "app")
import boto3
from botocore.config import Config
from common import BUCKET, ENDPOINT, LAB, model_key, read_env_file
root = read_env_file(LAB / ".env")
s3 = boto3.client("s3", endpoint_url=ENDPOINT, aws_access_key_id=root["MINIO_ROOT_USER"],
                  aws_secret_access_key=root["MINIO_ROOT_PASSWORD"], region_name="us-east-1",
                  config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
s3.put_object(Bucket=BUCKET, Key=model_key(sys.argv[1]), Body=os.urandom(200000))
PY
if $PY app/serve.py load "$NAME" >>.check.log 2>&1; then echo "FAIL  server loaded a tampered model"; fail=1
else echo "pass  server refuses a tampered model"; fi

# 7. the read is in the audit log, under the server's own identity
sleep 2
server_key=$($PY -c "import sys; sys.path.insert(0,'app'); from common import LAB, read_env_file; print(read_env_file(LAB/'config'/'server.env')['S3_ACCESS_KEY'])")
root_key=$($PY -c "import sys; sys.path.insert(0,'app'); from common import LAB, read_env_file; print(read_env_file(LAB/'.env')['MINIO_ROOT_USER'])")
$PY - "$AUDIT_DIR/audit.log" "$NAME/model.bin" "$server_key" "$root_key" <<'PY' || fail=1
import json, sys
path, obj, server_key, root_key = sys.argv[1:]
try:
    events = [json.loads(l) for l in open(path) if l.strip()]
except FileNotFoundError:
    events = []
reads = [e for e in events if e.get("api", {}).get("name") == "GetObject" and e["api"].get("object") == obj]
who = sorted({e.get("accessKey", "?") for e in reads})
if not events: print("FAIL  no audit events at all (is anything sending them to the collector?)"); sys.exit(1)
if server_key == root_key: print("FAIL  audit can't tell services apart: the server uses the admin login"); sys.exit(1)
if server_key in who: print(f"pass  audit log shows the server's download, as {server_key}")
else: print(f"FAIL  no audited download of {obj} by {server_key} (saw: {who or 'none'})"); sys.exit(1)
PY

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
