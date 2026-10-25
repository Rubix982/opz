# Lab 34 · Solution (spoilers)

## What was wrong

1. **The secret moved before the database did.** `put_secret_value` with no
   stage makes the new value `AWSCURRENT` immediately. If the database change
   then fails, every app reads a password the database doesn't know, and the
   app goes down (incident 2).
2. **The old password died instantly.** Apps fetch the secret and keep using it
   for a while. Changing the database password with no overlap breaks every
   connection made with the old one (incident 1).
3. **It never checked.** It didn't read the database's answer, didn't try the new
   password, and caught every exception, then exited 0. A 200 from the database
   (fault `ignore`) proves nothing.

## The fix: create, set, test, finish

`AWSCURRENT` moves **last**, only after the database has the new password and a
real login with it has worked. Any failure before that leaves apps on the old,
working secret, and exits nonzero.

```python
"""Rotates the orders database password in four steps, the way Secrets Manager does.

    python app/rotate.py     # exit 0 = rotated; nonzero = FAILED (and says where)

  1. create  put the new password in a version labelled AWSPENDING
             (reuse an AWSPENDING left behind by a failed run)
  2. set     change it in the database, keeping the current one valid too
  3. test    log in with the pending password
  4. finish  move AWSCURRENT to the new version (the old one becomes AWSPREVIOUS)

AWSCURRENT only moves after the database has the new password and it's been
proven to work. Any failure stops before that, so apps never see a broken secret.
"""

import json
import secrets as rand
import sys

from common import SECRET_ID, can_login, db_post, secrets

sm = secrets()


class RotationError(Exception):
    pass


def version_with(stage: str) -> str | None:
    for v in sm.list_secret_version_ids(SecretId=SECRET_ID)["Versions"]:
        if stage in v.get("VersionStages", []):
            return v["VersionId"]
    return None


def create() -> tuple[str, str]:
    pending = version_with("AWSPENDING")
    current = version_with("AWSCURRENT")
    if pending and pending != current:
        value = sm.get_secret_value(SecretId=SECRET_ID, VersionId=pending)["SecretString"]
        return pending, json.loads(value)["password"]
    new = "pw_FAKE_" + rand.token_hex(12)
    version = sm.put_secret_value(SecretId=SECRET_ID, VersionStages=["AWSPENDING"],
                                  SecretString=json.dumps({"username": "app", "password": new}))["VersionId"]
    return version, new


def set_in_db(password: str) -> None:
    status = db_post("/admin/password", {"user": "app", "password": password, "retain_current": True}, admin=True)
    if status != 200:
        raise RotationError(f"database refused the change (HTTP {status})")


def test(password: str) -> None:
    if not can_login(password):
        raise RotationError("the new password doesn't log in; database change didn't take effect")


def finish(version: str) -> None:
    current = version_with("AWSCURRENT")
    sm.update_secret_version_stage(SecretId=SECRET_ID, VersionStage="AWSCURRENT",
                                   MoveToVersionId=version, RemoveFromVersionId=current)
    sm.update_secret_version_stage(SecretId=SECRET_ID, VersionStage="AWSPENDING", RemoveFromVersionId=version)


def main() -> int:
    step = "create"
    try:
        version, password = create()
        step = "set"
        set_in_db(password)
        step = "test"
        test(password)
        step = "finish"
        finish(version)
    except Exception as e:
        print(f"ROTATION FAILED at step '{step}': {e}", file=sys.stderr)
        return 1
    print(f"rotated: version {version[:8]} is now AWSCURRENT")
    return 0


sys.exit(main())
```

| Step | What it does | If it fails |
|---|---|---|
| create | new version labelled `AWSPENDING` (apps can't see it) | nothing changed |
| set | DB password changed, **old one retained** | apps still on old secret, old password still valid |
| test | log in with the pending password | same; this catches the "200 but not applied" bug |
| finish | `AWSCURRENT` → new version; old becomes `AWSPREVIOUS` | the point of no return, and only reached once everything works |

A failed run leaves its `AWSPENDING` version behind. The next run reuses it, so
the password it may have half-set in the database still matches.

## Details worth knowing

- **This is exactly the AWS Lambda rotation contract.** Secrets Manager calls
  your function with `Step=createSecret|setSecret|testSecret|finishSecret`. AWS's
  template functions have the same shape as the code above.
- **Overlap strategies.** Here the database keeps two passwords for one user
  (MySQL 8 `RETAIN CURRENT PASSWORD`, Redis ACL users can hold several).
  Databases that can't do that use the **alternating users** strategy: two users,
  `app_a` and `app_b`; each rotation changes the inactive one and then flips.
  AWS ships both templates.
- **Apps must re-fetch.** The overlap only lasts until the *next* rotation. Apps
  should cache the secret for minutes, not forever, and re-fetch on an auth
  failure (lab 10).
- **Alerting on real AWS:** an EventBridge rule on the `RotationFailed` event
  (and on `RotationAbandoned`) to SNS or a pager, plus an alarm if
  `LastRotatedDate` gets older than the schedule. A failure that only goes to a
  log is the incident you just fixed.
- **What this doesn't cover:** *why* the database was unreachable. On AWS the
  usual cause is a Lambda in a subnet with no route to the database, or a
  security group missing the rule. The fix here makes that failure visible and
  harmless; somebody still has to fix the network.
