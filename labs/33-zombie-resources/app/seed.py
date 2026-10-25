"""Builds the "account": two years of experiments, backups and forgotten things.

    python app/seed.py                   # fill the emulator
    python app/seed.py --manifest out.json   # (used by check.sh) also write what's what

Run it once against a fresh emulator. ./setup.sh does that for you.
"""

import json
import sys
import time

from common import ec2

FUTURE, PAST_1, PAST_2 = "2099-12-31", "2026-01-31", "2026-03-01"
c = ec2()


def tags(owner: str | None, expires: str | None, **extra: str) -> list[dict]:
    t = [{"Key": "Name", "Value": extra.pop("name", "")}]
    if owner:
        t.append({"Key": "owner", "Value": owner})
    if expires:
        t.append({"Key": "expires", "Value": expires})
    t += [{"Key": k, "Value": v} for k, v in extra.items()]
    return [x for x in t if x["Value"]]


def volume(t: list[dict], size: int = 20) -> str:
    spec = [{"ResourceType": "volume", "Tags": t}] if t else []
    return c.create_volume(AvailabilityZone="us-east-1a", Size=size, TagSpecifications=spec)["VolumeId"]


def snapshot(vol: str, t: list[dict]) -> str:
    spec = [{"ResourceType": "snapshot", "Tags": t}] if t else []
    return c.create_snapshot(VolumeId=vol, TagSpecifications=spec)["SnapshotId"]


def instance(image: str, t: list[dict], stopped: bool = False) -> tuple[str, str]:
    spec = [{"ResourceType": "instance", "Tags": t}, {"ResourceType": "volume", "Tags": t}] if t else []
    i = c.run_instances(ImageId=image, MinCount=1, MaxCount=1, InstanceType="t3.micro",
                        TagSpecifications=spec)["Instances"][0]
    if stopped:
        c.stop_instances(InstanceIds=[i["InstanceId"]])
    return i["InstanceId"], i["BlockDeviceMappings"][0]["Ebs"]["VolumeId"]


# The platform team's base image, which every instance is launched from.
platform = tags("platform-team", FUTURE, name="base-image-source")
base_src = volume(platform, 8)
base_snap = snapshot(base_src, platform)
base_ami = c.register_image(Name="base-2025", RootDeviceName="/dev/sda1",
                            BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"SnapshotId": base_snap}}])["ImageId"]

web, web_root = instance(base_ami, tags("web-team", FUTURE, name="web-1"))
mystery, mystery_root = instance(base_ami, [])                                            # who made this?
old_exp, old_exp_root = instance(base_ami, tags("saif", PAST_1, name="gpu-experiment"), stopped=True)
forgotten, forgotten_root = instance(base_ami, [], stopped=True)
parked, parked_root = instance(base_ami, tags("ml-team", FUTURE, name="eval-box"), stopped=True)

db_data = volume(tags("web-team", FUTURE, name="web-1-data"), 100)
c.attach_volume(VolumeId=db_data, InstanceId=web, Device="/dev/sdf")
spare = volume(tags("data-team", FUTURE, name="restore-spare"), 500)                      # kept on purpose
orphan = volume([], 250)                                                                    # detached years ago
expired = volume(tags("saif", PAST_2, name="dataset-scratch"), 1000)
scratch = volume([], 50)
c.attach_volume(VolumeId=scratch, InstanceId=mystery, Device="/dev/sdf")

# The nightly backup job: one snapshot of web-1-data per night, never deleted.
nightly = []
for n in range(8):
    nightly.append(snapshot(db_data, tags("web-team", FUTURE, name=f"web-1-data nightly {n + 1}")))
    time.sleep(1.1)  # so each one has a distinct StartTime
# Someone once built an image from the oldest backup, and it's still in use.
golden_ami = c.register_image(Name="web-golden", RootDeviceName="/dev/sda1",
                              BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"SnapshotId": nightly[0]}}])["ImageId"]

# An old dataset: its volume was deleted long ago, but its snapshot never was.
dataset = volume(tags("saif", PAST_1, name="dataset-2024"), 2000)
dataset_snap = snapshot(dataset, tags("saif", PAST_1, name="dataset-2024 final copy"))
c.delete_volume(VolumeId=dataset)

# moto quirk: registering an AMI makes its own copy of the snapshot (untagged,
# pointing at a volume that doesn't exist). Real AWS would use our snapshot.
# Tag the copies the way their sources are tagged, so they look like ours.
ami_snaps = []
for image, source in ((base_ami, platform), (golden_ami, tags("web-team", FUTURE, name="web-golden image"))):
    for m in c.describe_images(ImageIds=[image])["Images"][0]["BlockDeviceMappings"]:
        ami_snaps.append(m["Ebs"]["SnapshotId"])
        c.create_tags(Resources=[m["Ebs"]["SnapshotId"]], Tags=source)

eip_web = c.allocate_address(Domain="vpc")["AllocationId"]
c.associate_address(AllocationId=eip_web, InstanceId=web)
eip_loose = c.allocate_address(Domain="vpc")["AllocationId"]                               # $3.60/month, forever

print(f"seeded: 5 instances, {len(c.describe_volumes()['Volumes'])} volumes, "
      f"{len(c.describe_snapshots(OwnerIds=['self'])['Snapshots'])} snapshots, 2 Elastic IPs")

if "--manifest" in sys.argv:
    manifest = {
        "zombie": [old_exp, forgotten, orphan, expired, *nightly[:5], dataset_snap, eip_loose],
        "untagged": [mystery, mystery_root, forgotten, forgotten_root, orphan, scratch],
        "keep": [web, web_root, mystery, mystery_root, parked, parked_root, db_data, spare, scratch,
                 base_src, base_snap, *ami_snaps, *nightly[5:], eip_web, base_ami, golden_ami],
    }
    with open(sys.argv[sys.argv.index("--manifest") + 1], "w") as f:
        json.dump(manifest, f)
