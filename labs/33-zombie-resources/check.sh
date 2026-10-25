#!/usr/bin/env bash
# Seeds a fresh account in its own emulator (port 9133), then runs your janitor
# twice. Passes only when:
#   - the default run only reports: it lists exactly the zombies and exactly the
#     untagged resources, and changes nothing;
#   - the --delete run removes exactly the zombies and leaves every resource
#     that's in use, tagged and unexpired, or needed by an AMI.
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python; [ -x "$PY" ] || { echo "run ./setup.sh first (makes .venv)"; exit 1; }
export AWS_ENDPOINT_URL=http://localhost:9133
MANIFEST="$(mktemp)"; REPORT="$(mktemp)"
fail=0

docker rm -f opz-lab33-check >/dev/null 2>&1
docker run -d --name opz-lab33-check -e MOTO_EC2_LOAD_DEFAULT_AMIS=false -p 9133:5000 motoserver/moto:5.1.4 >/dev/null
trap 'docker rm -f opz-lab33-check >/dev/null 2>&1; rm -f "$MANIFEST" "$REPORT"' EXIT
for _ in $(seq 1 40); do curl -s localhost:9133 >/dev/null && break; sleep 0.5; done
echo "      seeding a fresh account (~10s)..."
$PY app/seed.py --manifest "$MANIFEST" >.check.log 2>&1 || { echo "FAIL  seeding crashed; see .check.log"; exit 1; }

inventory() {
  $PY - <<'PY'
import sys
sys.path.insert(0, "app")
from common import ec2
c = ec2()
ids = [i["InstanceId"] for r in c.describe_instances()["Reservations"] for i in r["Instances"] if i["State"]["Name"] != "terminated"]
ids += [v["VolumeId"] for v in c.describe_volumes()["Volumes"]]
ids += [s["SnapshotId"] for s in c.describe_snapshots(OwnerIds=["self"])["Snapshots"]]
ids += [a["AllocationId"] for a in c.describe_addresses()["Addresses"]]
ids += [i["ImageId"] for i in c.describe_images(Owners=["self"])["Images"]]
print("\n".join(sorted(ids)))
PY
}

compare() {  # label, expected-key, report-prefix
  $PY - "$MANIFEST" "$REPORT" "$2" "$3" "$1" <<'PY'
import json, sys
manifest, report, key, prefix, label = sys.argv[1:]
want = set(json.load(open(manifest))[key])
got = {line.split()[1] for line in open(report) if line.startswith(prefix + " ") and len(line.split()) > 1}
if got == want:
    print(f"pass  {label}: all {len(want)} found, nothing extra"); sys.exit(0)
print(f"FAIL  {label}: missed {len(want - got)}, wrongly listed {len(got - want)}")
for i in sorted(want - got): print(f"        missed   {i}")
for i in sorted(got - want): print(f"        extra    {i}")
sys.exit(1)
PY
}

before=$(inventory)
$PY app/janitor.py >"$REPORT" 2>>.check.log
after=$(inventory)
if [ "$before" = "$after" ]; then echo "pass  default run changed nothing"
else echo "FAIL  default run deleted things: $(comm -23 <(echo "$before") <(echo "$after") | tr '\n' ' ')"; fail=1; fi
compare "ZOMBIE lines  " zombie ZOMBIE || fail=1
compare "UNTAGGED lines" untagged UNTAGGED || fail=1

if [ "$fail" = 0 ]; then
  $PY app/janitor.py --delete >"$REPORT" 2>>.check.log
  now=$(inventory)
  $PY - "$MANIFEST" <<PY || fail=1
import json, sys
m = json.load(open(sys.argv[1])); now = set("""$now""".split())
left = [z for z in m["zombie"] if z in now]; lost = [k for k in m["keep"] if k not in now]
print("pass  --delete removed every zombie" if not left else f"FAIL  --delete left {len(left)} zombies: {' '.join(left)}")
print("pass  --delete kept everything in use, owned or needed by an AMI" if not lost else f"FAIL  --delete destroyed {len(lost)} resources it should have kept: {' '.join(lost)}")
sys.exit(1 if left or lost else 0)
PY
else
  echo "      (skipping the --delete run until the report is right)"
fi

[ "$fail" = 0 ] && echo "LAB PASSED" || echo "lab not passed yet"
exit $fail
