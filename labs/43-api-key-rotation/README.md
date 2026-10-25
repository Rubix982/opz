# Lab 43 · API Gateway Key Rotation Breaks Clients

**Time:** ~45 min · **Needs:** Docker, Python 3 · **Cost:** free. Runs against a
local AWS emulator, not a real account.

## The incident

The security review said API keys older than 90 days must be rotated, so
someone ran the runbook's `app/rotate.py billing` on a Tuesday afternoon. The
billing service went down at once: every request got `403 Forbidden` until an
engineer found the new key in a terminal scrollback, pasted it into billing's
config and redeployed, 40 minutes later.

Next quarter it's the reports service's turn, and nobody is sure every copy of
reports is even known. One old batch job may still have the old key.

## About the emulator

The API keys and the usage plan live in [moto](https://github.com/getmoto/moto),
a local fake of the AWS APIs, in a Docker container on `localhost:9043`. The
code makes ordinary `boto3` API Gateway calls (`create_api_key`,
`create_usage_plan_key`, `update_api_key`…), the same as against real AWS. Only
`endpoint_url` differs.

What's different from real AWS:
- moto stores keys but doesn't serve traffic, so `app/gateway.py` plays the
  gateway: it accepts a request when its `x-api-key` is an enabled key on the
  `partners` usage plan. It caches the key list for 3 seconds. Real API Gateway
  also takes time to notice a new key, though usually longer.
- moto doesn't implement `GetUsage` (per-key usage), so the gateway is the only
  place that can tell you who uses which key.
- `keys/<client>.key` stands in for a secret store (Secrets Manager, Vault, a
  Kubernetes Secret). Clients re-read it before every request.
- Every key is FAKE.

## Setup

```bash
./setup.sh                          # emulator on :9043, .venv, API + usage plan + 3 keys
source .venv/bin/activate
python app/gateway.py               # terminal 1: the gateway on :8043
python app/clients.py               # terminal 2: billing, reports, mobile calling it
python app/rotate.py billing        # terminal 3: the runbook step. Watch terminal 2.
```

Run `./setup.sh` again to reset everything.

## Your job

1. **Watch it break.** Run the rotation with the clients running. Why is billing
   locked out, and what would it have taken to avoid that?
2. **Make rotation safe.** Change `app/rotate.py`, and `app/gateway.py` where
   you need to, so a rotation never refuses a legitimate request. Hints, one at
   a time if you're stuck:
   - Two keys can be valid at once. What's the order: create, hand out,
     retire? And who hands the new key to the client?
   - The gateway caches its key list. What happens if a client gets its new key
     before the gateway knows about it?
   - Before you retire the old key you need to know nobody uses it any more.
     Where could that be measured? Look at what the gateway records today.
   - Disable before you delete: a disabled key can be re-enabled in one call
     if something you missed starts failing.
   - What should the script do if the old key is *still* in use after a fair
     wait? (`ROTATE_DRAIN_TIMEOUT` is a good name for "a fair wait".)
3. **Prove it.** `./check.sh` runs a fresh emulator and gateway, keeps the
   clients calling, and rotates twice:
   - **billing**, with every client re-reading its key: no request may be
     refused, billing must end on a new key, and the old key must stop working.
   - **reports**, while one copy of reports keeps the old key: the rotation
     must refuse to finish (nonzero exit) and leave the old key working.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why billing was locked out:
- The safe order of a rotation, step by step:
- Why the gateway's cache matters to that order:
- How the script knows the old key is unused, and what it does when it isn't:
- Why disable first and delete later:
