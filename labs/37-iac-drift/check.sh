#!/usr/bin/env bash
# Part 1, on a fresh emulator (port 9137) and a fresh state built from your code:
#   - applying infra/ from scratch already includes the emergency fix
#   - your drift check exits 0 on a clean environment
#   - after a new hand change it exits non-zero and names the drifted resource
#   - after reconciling, plan shows no changes and the drift check is green again
# Part 2, on your own environment (./setup.sh, then your work):
#   - plan shows no changes (reconciled)
#   - the emergency rule is still live; the unwanted hand changes are gone
set -u
cd "$(dirname "$0")"
LAB="$PWD"
fail=0
pass() { echo "pass  $*"; }
flunk() { echo "FAIL  $*"; fail=1; }

live() {  # project, python snippet using ec2/s3/sg -> prints a value
  docker compose -p "$1" exec -T aws python - <<PY 2>/dev/null
import boto3
kw = dict(endpoint_url="http://127.0.0.1:5000", region_name="us-east-1",
          aws_access_key_id="testing", aws_secret_access_key="testing")
ec2, s3 = boto3.client("ec2", **kw), boto3.client("s3", **kw)
sg = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["web"]}])["SecurityGroups"][0]
$2
PY
}
HAS_9100='print(any(p.get("FromPort") == 9100 and any(r["CidrIp"] == "10.42.0.0/16" for r in p["IpRanges"]) for p in sg["IpPermissions"]))'

# ---------- part 1: fresh environment -----------------------------------------
P=opz-lab37-check
rm -rf .check-work && mkdir -p .check-work
cp infra/*.tf .check-work/ && cp infra/.terraform.lock.hcl .check-work/ 2>/dev/null
AWS_PORT=9137 docker compose -p $P up -d --wait >.check.log 2>&1 || { echo "emulator didn't start; see .check.log"; exit 1; }
trap 'docker compose -p '$P' down -v >/dev/null 2>&1; rm -rf "$LAB/.check-work"' EXIT
export TF_DIR="$LAB/.check-work" COMPOSE_PROJECT=$P

if tools/tf.sh init -no-color >>.check.log 2>&1 && tools/tf.sh apply -auto-approve -no-color >>.check.log 2>&1; then
  pass "infra/ applies cleanly from scratch"
else
  flunk "infra/ doesn't apply from scratch; see .check.log"; echo "lab not passed yet"; exit 1
fi

[ "$(live $P "$HAS_9100")" = True ] && pass "the emergency fix (9100 from 10.42.0.0/16) is in code" \
  || flunk "a fresh apply from code doesn't open 9100 to monitoring: the next apply would undo the emergency fix"

tools/drift-check.sh >.check-drift.log 2>&1; rc=$?
[ "$rc" = 0 ] && pass "drift check is green on a clean environment" \
  || flunk "drift check exits $rc on a clean environment (false alarm)"

# a new hand change, not the one from the incident
live $P '
ec2.authorize_security_group_ingress(GroupId=sg["GroupId"], IpPermissions=[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}])
print("ok")' >/dev/null
tools/drift-check.sh >.check-drift.log 2>&1; rc=$?
if [ "$rc" != 0 ] && grep -q "aws_security_group.web" .check-drift.log; then
  pass "drift check fails (exit $rc) after a hand change and names aws_security_group.web"
elif [ "$rc" != 0 ]; then
  flunk "drift check fails (exit $rc) but its output doesn't say what drifted"
else
  flunk "SSH opened to the world by hand, and the drift check still exits 0"
fi

tools/tf.sh apply -auto-approve -no-color >>.check.log 2>&1
tools/tf.sh plan -detailed-exitcode -no-color >>.check.log 2>&1; rc=$?
tools/drift-check.sh >/dev/null 2>&1; rc2=$?
[ "$rc" = 0 ] && [ "$rc2" = 0 ] && pass "after reconciling: plan shows no changes and the drift check is green" \
  || flunk "after reconciling: plan exit $rc, drift check exit $rc2 (both should be 0)"
rm -f .check-drift.log

# ---------- part 2: your environment -------------------------------------------
unset TF_DIR COMPOSE_PROJECT
if ! docker compose -p opz-lab37 ps --status running 2>/dev/null | grep -q aws; then
  flunk "your environment isn't running: ./setup.sh, then reconcile it"
else
  tools/tf.sh plan -detailed-exitcode -no-color >>.check.log 2>&1; rc=$?
  [ "$rc" = 0 ] && pass "your environment: plan shows no changes" \
    || flunk "your environment: plan exit $rc (2 = still drifted or code not applied, 1 = error)"
  [ "$(live opz-lab37 "$HAS_9100")" = True ] && pass "your environment: monitoring can still scrape on 9100" \
    || flunk "your environment: the 9100 rule is gone, so alerting is blind again"
  v=$(live opz-lab37 'print(s3.get_bucket_versioning(Bucket="opz-lab37-reports").get("Status"))')
  [ "$v" = Enabled ] && pass "your environment: report versioning is back on" \
    || flunk "your environment: report versioning is '$v' (the hand change from the incident is still live, or was codified)"
  t=$(live opz-lab37 'print(sorted((t["Key"], t["Value"]) for t in sg.get("Tags", []) if t["Key"] in ("env", "edited-by")))')
  [ "$t" = "[('env', 'prod')]" ] && pass "your environment: tags match the tagging standard" \
    || flunk "your environment: security group tags $t (expected only env=prod)"
fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
