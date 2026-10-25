# Lab 33 · Zombie Resources Driving Up Cloud Bill

**Time:** ~60 min · **Needs:** Docker, Python 3 · **Cost:** free. Runs against a
local AWS emulator, not a real account.

Also covers: *Forgotten EBS Snapshots Bloat Monthly Bill*.

## The incident

The AWS bill has crept up every month for a year. Finance wants it explained.
Nobody remembers making half of what's running.

Last quarter someone wrote `app/janitor.py` to clean up, and ran it once "to see
what it would do". It deleted the data team's 500 GB restore volume and the
volume the base image is built from. It's been banned ever since, and the bill
kept growing.

Your job is to write the janitor that should have existed: one that **reports by
default**, deletes only when asked, and can tell waste from things people need.

## About the emulator

The "account" is [moto](https://github.com/getmoto/moto), a local fake of the AWS
APIs, in Docker on `localhost:9033`. The code makes ordinary `boto3` EC2 calls,
the same ones you'd make against real AWS. Only `endpoint_url` differs. What's
different:

- **AMI snapshots.** Registering an AMI from a snapshot makes moto create its own
  copy of the snapshot, pointing at a volume that doesn't exist. Real AWS would
  use your snapshot directly. The seed tags those copies so they look like the
  rest of the account.
- **No real deletion guard.** Real AWS refuses to delete a snapshot that an AMI
  uses. moto lets you, so here your janitor is the only guard.
- **No billing.** Cost Explorer isn't emulated. The prices in the hints are the
  real list prices.
- **Time doesn't pass.** moto can't backdate a snapshot, so "keep the newest N"
  stands in for "keep N days".

## Setup

```bash
./setup.sh                        # emulator + .venv + seeds the account (~15s)
source .venv/bin/activate
python app/janitor.py --dry-run   # careful: without --dry-run the old one deletes
```

Explore with plain boto3 (`from common import ec2; c = ec2()` in `app/`), e.g.
`c.describe_volumes()`, `c.describe_snapshots(OwnerIds=["self"])`,
`c.describe_instances()`, `c.describe_addresses()`, `c.describe_images(Owners=["self"])`.
Re-run `./setup.sh` to reset the account after deleting things.

## The policy (what your janitor must enforce)

Every instance, volume and snapshot must carry two tags: `owner` and `expires`
(`YYYY-MM-DD`). That's the tagging policy the account is adopting. A resource is a
**zombie** when:

| Resource | Zombie when |
|---|---|
| Volume | unattached (`available`), **and** untagged or expired |
| Instance | `stopped`, **and** untagged or expired. A *running* untagged instance is only reported: it might be serving someone. |
| Snapshot | **not used by any AMI**, and either its source volume no longer exists, or it's older than the newest 3 snapshots of the same volume |
| Elastic IP | not associated with anything |

**Output contract** (check.sh reads it):
- `python app/janitor.py` prints `ZOMBIE <id> <reason>` for each zombie and
  `UNTAGGED <id>` for each instance, volume or snapshot missing a required tag,
  and **changes nothing**.
- `python app/janitor.py --delete` prints the same, then deletes or terminates
  each zombie (`DELETED <id>`).

## Your job

1. **Run the old janitor with `--dry-run`** and list what's wrong with it before
   writing anything. Hints, one at a time:
   - What does it do when you run it with no flags? What should a cleanup tool do?
   - Which "unattached volume" did the data team need? How could the janitor have known?
   - Why does a stopped instance still cost money? (Its volumes. An Elastic IP
     costs ~$3.60/month whether you use it or not.)
2. **Rewrite `app/janitor.py`** to the policy and output contract above.
   - Snapshots are billed for the data they hold, and a backup job that never
     deletes adds one every night. Group snapshots by `VolumeId` and sort by `StartTime`.
   - Which snapshots must never go, however old? Look at what each AMI's
     `BlockDeviceMappings` points to.
3. **Prove it.** `./check.sh` seeds a fresh account in its own emulator (port
   9133), runs your janitor in report mode (it must find exactly the zombies and
   the untagged resources, and change nothing), then with `--delete` (exactly the
   zombies must go, nothing else).
4. **Write the retro** (below). **Clean up:** `./teardown.sh` deletes the whole "account".

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- The three things wrong with the old janitor:
- Why tags make cleanup decidable (what can't you tell without them?):
- What still costs money when an instance is stopped:
- Why a snapshot of a deleted volume is the classic forgotten cost, and when it isn't waste:
- How infrastructure-as-code (Terraform, CloudFormation) prevents zombies in the first place:
