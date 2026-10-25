# Lab 33 · Solution (spoilers)

## What was wrong with the old janitor

1. **It deleted by default.** "Show me" needed `--dry-run`; forgetting the flag
   destroyed things. A destructive tool should do nothing unless told
   explicitly: report by default, `--delete` to act.
2. **"Unattached" isn't "unused".** The restore spare and the base-image source
   are unattached on purpose. Without tags there's no way to tell a spare from
   waste, so the old janitor guessed, wrongly.
3. **It only knew about volumes.** Stopped instances, snapshots piling up from
   the nightly job, a snapshot of a long-deleted 2 TB volume and a loose Elastic
   IP were all invisible to it.

## The janitor

Tags turn "is this waste?" from a judgement call into a rule: no owner, or past
its `expires` date, and not in use.

```python
"""Cost janitor: reports by default, deletes only with --delete.

    python app/janitor.py            # report: ZOMBIE <id> <reason> and UNTAGGED <id> lines
    python app/janitor.py --delete   # report, then delete the zombies (DELETED <id>)

Policy:
  - every instance, volume and snapshot carries `owner` and `expires` (YYYY-MM-DD)
  - zombie volume:    unattached, and untagged or expired
  - zombie instance:  stopped, and untagged or expired (running ones are only reported)
  - zombie snapshot:  not used by any AMI, and either its volume is gone or it's
                      older than the newest KEEP_SNAPSHOTS of the same volume
  - zombie Elastic IP: not associated with anything
"""

import sys
from collections import defaultdict
from datetime import date

from common import ec2

KEEP_SNAPSHOTS = 3
REQUIRED = ("owner", "expires")
DELETE = "--delete" in sys.argv
TODAY = date.today().isoformat()
c = ec2()


def tag_map(resource: dict) -> dict:
    return {t["Key"]: t["Value"] for t in resource.get("Tags", [])}


def untagged(resource: dict) -> bool:
    return not all(k in tag_map(resource) for k in REQUIRED)


def expired(resource: dict) -> bool:
    exp = tag_map(resource).get("expires")
    return exp is not None and exp < TODAY


zombies: list[tuple[str, str, str]] = []  # (kind, id, reason)

instances = [i for r in c.describe_instances()["Reservations"] for i in r["Instances"]
             if i["State"]["Name"] != "terminated"]
for i in instances:
    if untagged(i):
        print(f"UNTAGGED {i['InstanceId']}")
    if i["State"]["Name"] == "stopped" and (untagged(i) or expired(i)):
        zombies.append(("instance", i["InstanceId"], "stopped and " + ("untagged" if untagged(i) else "expired")))

for v in c.describe_volumes()["Volumes"]:
    if untagged(v):
        print(f"UNTAGGED {v['VolumeId']}")
    if v["State"] == "available" and (untagged(v) or expired(v)):
        zombies.append(("volume", v["VolumeId"], "unattached and " + ("untagged" if untagged(v) else "expired")))

in_use_by_ami = {m["Ebs"]["SnapshotId"] for img in c.describe_images(Owners=["self"])["Images"]
                 for m in img.get("BlockDeviceMappings", []) if "Ebs" in m and "SnapshotId" in m["Ebs"]}
by_volume: dict[str, list[dict]] = defaultdict(list)
for s in c.describe_snapshots(OwnerIds=["self"])["Snapshots"]:
    if untagged(s):
        print(f"UNTAGGED {s['SnapshotId']}")
    by_volume[s["VolumeId"]].append(s)
volumes = {v["VolumeId"] for v in c.describe_volumes()["Volumes"]}
for vol, snaps in by_volume.items():
    snaps.sort(key=lambda s: s["StartTime"], reverse=True)
    for n, s in enumerate(snaps):
        if s["SnapshotId"] in in_use_by_ami:
            continue
        if vol not in volumes:
            zombies.append(("snapshot", s["SnapshotId"], f"its volume {vol} no longer exists"))
        elif n >= KEEP_SNAPSHOTS:
            zombies.append(("snapshot", s["SnapshotId"], f"older than the newest {KEEP_SNAPSHOTS} of {vol}"))

for a in c.describe_addresses()["Addresses"]:
    if not a.get("AssociationId"):
        zombies.append(("eip", a["AllocationId"], "Elastic IP not attached to anything"))

for kind, rid, reason in zombies:
    print(f"ZOMBIE {rid} {kind}: {reason}")

if DELETE:
    for kind, rid, _ in zombies:
        if kind == "instance":
            c.terminate_instances(InstanceIds=[rid])
        elif kind == "volume":
            c.delete_volume(VolumeId=rid)
        elif kind == "snapshot":
            c.delete_snapshot(SnapshotId=rid)
        elif kind == "eip":
            c.release_address(AllocationId=rid)
        print(f"DELETED {rid}")
```

On the seeded account it finds 11 zombies:

| Zombie | Why |
|---|---|
| 2 stopped instances | one expired, one untagged |
| 2 volumes | one untagged, one expired (the 1 TB scratch) |
| 5 nightly snapshots | older than the newest 3 of their volume |
| 1 snapshot of `dataset-2024` | its volume is long gone |
| 1 Elastic IP | attached to nothing |

It keeps the restore spare (tagged, not expired), the parked eval box (stopped
but tagged), the untagged *running* instance (reported for an owner to claim, not
killed) and both AMI snapshots.

## Details worth knowing

- **Never delete what an AMI uses.** Here the AMI snapshots look exactly like
  orphans (their volume is gone), so only the AMI check saves them. On real AWS
  the API refuses that deletion, but a janitor shouldn't rely on that.
- **Report, then act.** In practice the report goes to the owners first ("these
  get deleted Friday unless tagged"), and deletion runs later. Many teams also
  snapshot a volume *before* deleting it, with a short expiry, as an undo button.
- **The managed versions of this:** AWS Config's `required-tags` rule flags
  untagged resources. Tag policies in AWS Organizations enforce tag values. Data
  Lifecycle Manager keeps the last N snapshots automatically, so you don't need
  a cron job. S3 lifecycle rules do the same for objects.
- **The real prevention is infrastructure as code.** Resources made by
  Terraform are listed in its state, so `terraform destroy` removes exactly what
  it made. Things clicked together in the console are the ones that turn into zombies.
- **What this doesn't cover:** the other big zombie categories. Idle load
  balancers, NAT gateways (~$32/month each, plus data), old RDS snapshots,
  CloudWatch log groups with no retention, and anything in *another region*.
  A janitor that only looks at `us-east-1` misses the experiment someone ran in
  `eu-west-1`.
