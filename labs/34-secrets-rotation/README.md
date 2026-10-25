# Lab 34 · Secrets Manager Rotation Fails Silently

**Time:** ~50 min · **Needs:** Docker, Python 3 · **Cost:** free. Runs against a
local AWS emulator, not a real account.

## The incident

The orders database password is rotated nightly by `app/rotate.py`, and the
password lives in Secrets Manager as `orders/db`. Two things happened this month:

- After one rotation, every running app instance lost its database connection at
  the same moment. They came back after a restart.
- One morning the whole app was down: the secret held a password the database
  had never heard of. The rotation log from the night before said only
  `warning: rotation hiccup`, and the job exited 0, so nobody was paged.

## About the emulator

Secrets Manager is [moto](https://github.com/getmoto/moto), a local fake of the
AWS APIs, in Docker on `localhost:9034`. The code makes the same `boto3` calls
you'd make against real AWS. The "database" is `db/server.py`, a tiny stand-in
that only checks passwords. What's different from real AWS:

- On AWS, rotation runs as a **Lambda function** that Secrets Manager calls four
  times, once per step (`createSecret`, `setSecret`, `testSecret`,
  `finishSecret`), and a failure emits a `RotationFailed` event you can alert on
  with EventBridge. Here one script runs all four steps, and "alerting" means
  exiting nonzero with a clear message, which is what a cron job or CI runner
  can page on.
- moto's `get_secret_value` with no stage can return a stale version after labels
  move. The app asks for `VersionStage="AWSCURRENT"` by name, which on real AWS
  means the same thing as the default.

## Setup

```bash
./setup.sh                          # emulator + .venv + the secret
python3 db/server.py                # terminal 2: the database on :8034
source .venv/bin/activate
python app/app.py                   # the app logs in with the current secret
python tools/versions.py            # every version, its labels, and whether it logs in
python app/rotate.py; python app/app.py; python tools/versions.py
tools/fault.sh down                 # break the DB's password changes; try rotating again
tools/fault.sh ignore               # a nastier failure: "OK" but nothing changed
tools/fault.sh none
```

Restart `db/server.py` and re-run `./setup.sh` to reset.

## Your job

1. **Explain both incidents** from `rotate.py` alone. Hints, one at a time:
   - In what order does it change the secret and the database? What do apps see
     if the second step fails?
   - What happens to an app that fetched the password a minute ago, the instant
     the database password changes?
   - Look at the `except`. Who finds out when it fails?
2. **Rewrite `app/rotate.py`** so a rotation can fail at any step without taking
   the app down, and every failure is loud.
   - Secrets Manager versions carry **staging labels**: `AWSCURRENT` (what apps
     read), `AWSPENDING` (being rotated in), `AWSPREVIOUS` (the one before).
     `put_secret_value(..., VersionStages=["AWSPENDING"])` stores a version
     without apps seeing it. `update_secret_version_stage` moves a label.
   - Read `db/server.py`. It supports keeping the old password valid during a
     change, as MySQL 8 does.
   - When is it safe to move `AWSCURRENT`? What must be true first?
   - A failed run may leave an `AWSPENDING` version behind. What should the next run do with it?
3. **Prove it.** `./check.sh` runs its own emulator (9134) and database (18034)
   and rotates four times: healthy, with the DB unreachable, with the change
   silently ignored, and healthy again. Apps must keep working throughout,
   failures must exit nonzero, and the healthy runs must really rotate.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`, and stop the database.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Incident 1, and why the old password needs to outlive the change:
- Incident 2, and why "store the new password first" was the wrong instinct:
- The four steps, and which one is the point of no return:
- What `testSecret` caught that a 200 from the database didn't:
- How you'd alert on this on real AWS:
