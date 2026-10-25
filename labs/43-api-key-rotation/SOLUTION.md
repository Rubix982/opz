# Lab 43 · Solution (spoilers)

## What went wrong

`rotate.py` did everything in one step: **deleted** the old key, created a new
one, and printed it for a human to paste into billing's config. From the moment
of the delete until the redeploy, billing had no valid key. There was nothing
to undo either, because the old key was gone, not disabled.

Two more gaps sit behind that one:
- Nothing hands the client its new key. The rotation ends at "print it".
- Nobody can tell who still uses a key. The gateway only counted totals.

## The fix

Rotate with an **overlap**: two valid keys for a while, the old one retired
only once you've watched it go quiet.

1. Create the new key and attach it to the usage plan. The old one keeps working.
2. Wait until the gateway **accepts** the new key. Its key cache (3 s here,
   longer on real API Gateway) has to catch up, or the client switches to a key
   the gateway still refuses. Handing the key out before this point is exactly
   the half-fix that still fails the check.
3. Hand the key to the client by writing its secret atomically (temp file +
   `os.replace`), so a client never reads half a key.
4. Watch per-key traffic until the new key is in use and the old one has been
   quiet for a few seconds. If the old key is still busy after
   `ROTATE_DRAIN_TIMEOUT`, **stop with a nonzero exit** and leave both enabled.
   Someone you don't know about depends on it.
5. **Disable** the old key. Delete it later (`--cleanup`), once nothing has
   needed it back.

The gateway needs per-key usage for step 4:

```python
usage: dict[str, dict] = {}  # key id -> {"name", "count", "last_seen"}
...
        if self.path == "/usage":
            with lock:
                self._send(200, usage)
            return
...
        key_id, key_name = key
        with lock:
            stats["ok"] += 1
            u = usage.setdefault(key_id, {"name": key_name, "count": 0, "last_seen": 0.0})
            u["count"] += 1
            u["last_seen"] = time.time()
```

And `app/rotate.py`:

```python
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

from common import GATEWAY_URL, KEYS_DIR, apigw, keys_for, plan_id

DRAIN_TIMEOUT = float(os.environ.get("ROTATE_DRAIN_TIMEOUT", "300"))
QUIET_FOR = 3.0  # old key counts as unused after this many seconds without traffic


def gateway_accepts(value: str) -> bool:
    req = urllib.request.Request(f"{GATEWAY_URL}/orders", headers={"x-api-key": value})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except urllib.error.HTTPError:
        return False


def usage() -> dict:
    with urllib.request.urlopen(f"{GATEWAY_URL}/usage", timeout=5) as r:
        return json.load(r)


def cleanup(ag, plan: str) -> None:
    for k in ag.get_api_keys()["items"]:
        if not k["enabled"]:
            ag.delete_usage_plan_key(usagePlanId=plan, keyId=k["id"])
            ag.delete_api_key(apiKey=k["id"])
            print(f"deleted disabled key {k['id']} ({k['name']})")


def main() -> int:
    ag = apigw()
    plan = plan_id(ag)
    if sys.argv[1] == "--cleanup":
        cleanup(ag, plan)
        return 0
    client = sys.argv[1]
    old = [k for k in keys_for(ag, client) if k["enabled"]]

    value = f"FAKE-{client}-{secrets.token_hex(10)}"
    new = ag.create_api_key(
        name=f"{client}-{time.strftime('%Y%m%d%H%M%S')}", enabled=True, value=value, tags={"client": client}
    )
    ag.create_usage_plan_key(usagePlanId=plan, keyId=new["id"], keyType="API_KEY")
    print(f"1. created {new['id']} and attached it; old keys still enabled: {[k['id'] for k in old]}")

    deadline = time.time() + 30
    while not gateway_accepts(value):
        if time.time() > deadline:
            print("2. the gateway never accepted the new key; stopping, nothing handed out", file=sys.stderr)
            return 1
        time.sleep(0.5)
    print("2. the gateway accepts the new key")

    path = KEYS_DIR / f"{client}.key"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(value + "\n")
    os.replace(tmp, path)
    print(f"3. handed the new key to {client} ({path})")
    # our own probe in step 2 used the new key; only count traffic after this
    baseline = usage().get(new["id"], {}).get("count", 0)

    deadline = time.time() + DRAIN_TIMEOUT
    while True:
        u = usage()
        now = time.time()
        new_seen = u.get(new["id"], {}).get("count", 0) > baseline
        busy = {k["id"]: now - u[k["id"]]["last_seen"] for k in old
                if k["id"] in u and now - u[k["id"]]["last_seen"] < QUIET_FOR}
        if new_seen and not busy:
            break
        if now > deadline:
            for kid, ago in busy.items():
                print(f"4. old key {kid} was used {ago:.1f}s ago; not disabling it", file=sys.stderr)
            if not new_seen:
                print("4. nothing has used the new key yet", file=sys.stderr)
            print("   Find who still has the old key, update them, and run this again.", file=sys.stderr)
            return 2
        time.sleep(0.5)
    print("4. the new key is in use and the old one has gone quiet")

    for k in old:
        ag.update_api_key(apiKey=k["id"], patchOperations=[{"op": "replace", "path": "/enabled", "value": "false"}])
        print(f"5. disabled old key {k['id']} ({k['name']}); delete it later with --cleanup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`check.sh`: no refused requests, a new key that works, the old one refused
afterwards; and with a straggler, exit 2 and the old key still working. Passed.

## Details worth knowing

- **Count only traffic after the hand-off.** The script's own probe in step 2
  uses the new key. If you count that, "the new key is in use" is true before
  any client has switched.
- **A fixed sleep isn't a check.** "Wait 10 seconds, then disable" passes when
  every client behaves and cuts off the one you didn't know about. That's the
  second half-fix the check catches.
- **On real AWS** the per-key signal is usage-plan usage (`GetUsage`) or the
  gateway's access logs with `$context.identity.apiKeyId`. Tag keys with their
  owner so a "still in use" message names a team, not an ID.
- **Two keys per client is normal.** Stripe, GitHub and AWS IAM access keys all
  allow two at once for this reason.
- **What this doesn't cover:** a *leaked* key. Then you rotate on purpose
  *without* waiting for the old key to go quiet, because the traffic on it might
  be the attacker's. Disable first, accept the breakage, and fix clients
  fast. Also not covered: how secrets reach real services (Secrets Manager
  rotation, CSI driver mounts, restarts for clients that read keys only at start).
