"""Cost janitor. Written in a hurry after last quarter's bill.

    python app/janitor.py              # ...
    python app/janitor.py --dry-run    # just show what it would delete
"""

import sys

from common import ec2

DRY_RUN = "--dry-run" in sys.argv
c = ec2()

# Unattached volumes cost money and do nothing.
for vol in c.describe_volumes()["Volumes"]:
    if vol["State"] == "available":
        print(f"ZOMBIE {vol['VolumeId']} unattached volume")
        if not DRY_RUN:
            c.delete_volume(VolumeId=vol["VolumeId"])
            print(f"DELETED {vol['VolumeId']}")

# TODO: snapshots, instances, Elastic IPs
