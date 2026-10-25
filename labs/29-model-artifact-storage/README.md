# Lab 29 · Protecting AI Model Artifacts

**Time:** ~60 min · **Needs:** Docker Compose, Python 3 · **Cost:** free, all local

> The model store is **MinIO**, an S3-compatible object store that many teams
> run on-prem for checkpoints. It enforces S3 bucket policies and IAM-style user
> policies the way AWS does, so what you learn here carries straight over to S3.

## The incident

Three things turned up in the same week:

1. A model checkpoint that cost months of GPU time showed up on a public model
   hub, uploaded by someone outside the company. The `models` bucket was readable
   without credentials "because it's internal", and an internal URL had leaked
   into a public notebook.
2. Production served garbage for an afternoon. Someone's training run had published to
   `sentiment/v3` instead of `v4` and overwrote the live model. There was no way
   to get the old weights back.
3. Nobody could say who downloaded the checkpoint, or who overwrote v3. Every
   service, and half the engineers, use the same admin login.

## Setup

```bash
./setup.sh                                      # model store on localhost:9029 + .venv
.venv/bin/python app/serve.py load sentiment/v3 # what the inference server does at startup
curl -s -o /dev/null -w '%{http_code}\n' localhost:9029/models/sentiment/v3/model.bin   # no login at all
head -c 1000 /dev/urandom > /tmp/v4.bin
.venv/bin/python app/train.py publish sentiment/v3 /tmp/v4.bin   # oops: published to v3
```

- The trainer reads its login from `config/trainer.env`, the server from `config/server.env`.
- `infra/init.sh` sets up the bucket. MinIO's admin tool is
  `docker compose exec init /opt/bitnami/minio-client/bin/mc`, already logged in
  as `local` once init has run.
- An audit collector already runs at `http://audit:8080/`. Anything sent there
  lands in `audit/audit.log`. Nothing sends to it yet.

## Your job

Make the store safe without stopping the trainer from publishing or the server from loading.

1. **Close it.** No anonymous reads. (Hint: what does `mc anonymous` set in `infra/init.sh`?)
2. **One login per service, least privilege.** The server only reads. The trainer
   publishes but can't delete. Neither uses the admin login.
   - Look up `mc admin user add`, `mc admin policy create` and `mc admin policy attach`.
     Policies are the same JSON as AWS IAM (`s3:GetObject`, `s3:PutObject`, ...).
   - `init.sh` can read `/config/*.env`; the config folder is mounted there.
3. **Make overwrites recoverable.** Look up bucket versioning.
4. **Refuse tampered weights.** Even with all of the above, someone holding the
   admin login could replace a file. The server should notice before it loads it.
   Where should the "right" checksum live so the same person can't change it too?
5. **Make access visible.** Point MinIO at the audit collector. Look up
   `MINIO_AUDIT_WEBHOOK_ENABLE_<name>` and `MINIO_AUDIT_WEBHOOK_ENDPOINT_<name>`.
6. **Prove it.** `./check.sh` builds a fresh copy of the stack from your files and
   tests every point above, as each identity in turn.
7. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Why "it's internal" wasn't protection:
- What each service's policy allows, and why that's enough:
- What versioning gives back, and what it costs:
- Where the checksum lives, and why not next to the weights:
- What the audit log can answer now that it couldn't before:
- What still isn't covered:
