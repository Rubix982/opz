# Lab 30 · S3 Bucket Data Leak

**Time:** ~40 min · **Needs:** Docker Compose, Python 3 · **Cost:** free, all local (no AWS account)

> **Runs against a local S3.** The bucket is served by MinIO, which speaks the
> S3 API and enforces bucket policies the way AWS does. Your boto3 calls, the
> policy JSON and presigned URLs work unchanged against real S3. What MinIO
> **doesn't** have is AWS's account-level guard rails: *Block Public Access*
> and *AWS Config* rules. They're covered in `SOLUTION.md`, because on real AWS
> they're half the fix.

## The incident

In March, someone made the `acme-customer-exports` bucket public "just for the
demo" so a partner could download the Q1 export. The demo ended and the bucket
stayed public. It now holds every export since, with names, emails and the last
four digits of cards. Nothing broke, so nobody noticed until a researcher emailed
security with a listing of the bucket.

## Setup

```bash
./setup.sh                                  # local S3 on localhost:9030 + .venv with boto3
.venv/bin/python app/exports.py             # terminal 2: the export service on :8030
```

Be the stranger who found the bucket name:

```bash
curl -s localhost:9030/acme-customer-exports/                      # list everything
curl -s localhost:9030/acme-customer-exports/2026/q1-export.csv    # download
```

And use the app the way the business does:

```bash
curl -s -XPOST --data-binary @sample/q2-export.csv localhost:8030/exports/brightline-q2
curl -s localhost:8030/exports/brightline-q2/share       # the link we send the partner
```

## Your job

1. **Find out how it's exposed.** Hints, one at a time if you're stuck:
   - Read `infra/init.sh`, the bucket's setup. What does the last line do?
   - `docker compose exec init /opt/bitnami/minio-client/bin/mc anonymous get-json local/acme-customer-exports`
     shows the bucket policy it produced. Who is `"Principal"`? Which actions?
   - How does the app's share link work? What would happen to it if you closed the bucket?
2. **Fix it** so that:
   - nobody without credentials can list or download anything,
   - the partner still gets a link, but it works for **one file** and **expires**
     after `SHARE_TTL_SECONDS` (the app already reads that variable),
   - the app keeps working.
   Fix it in `infra/init.sh` and `app/exports.py`, not by hand, so a rebuilt
   bucket comes out right. Hint: look up *presigned URLs* in boto3.
3. **Prove it.** `./check.sh` builds a fresh copy of the stack from your files
   and checks all of the above, including that a link stops working after its TTL.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- What the public policy allowed, action by action:
- How a presigned URL grants access without making anything public:
- Why the link must expire, and how I'd choose the TTL:
- What on real AWS would have stopped this before it happened (two settings):
- How we'd *notice* a public bucket next time, instead of hearing from a stranger:
