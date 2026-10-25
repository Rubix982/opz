# Lab 30 · Solution (spoilers)

## What was wrong

`mc anonymous set public` writes a bucket policy like this:

```json
{"Effect": "Allow", "Principal": {"AWS": ["*"]},
 "Action": ["s3:GetBucketLocation", "s3:ListBucket", "s3:GetObject", ...],
 "Resource": ["arn:aws:s3:::acme-customer-exports", "arn:aws:s3:::acme-customer-exports/*"]}
```

`Principal: *` means *anyone on the internet*, with no signature at all.
`ListBucket` lets them enumerate every key, so a stranger doesn't even need to
guess file names. The share link was just the object's plain URL, so it only
worked *because* the bucket was public. Closing the bucket breaks the partner flow,
which is how buckets end up re-opened.

## The fix

**1. Close the bucket** in `infra/init.sh`:

```bash
mc anonymous set none local/acme-customer-exports
```

(`none` is also the default, so deleting the line works too. Being explicit
documents the intent and resets a bucket someone opened by hand.)

**2. Share with presigned URLs** in `app/exports.py`:

```python
def share_link(name: str) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key_for(name)},
        ExpiresIn=SHARE_TTL_SECONDS,
    )
```

A presigned URL carries a signature made with the *app's* credentials, covering
one method, one key and an expiry time. Anyone holding the URL can do exactly that
one thing until it expires. Nothing is public, and the link dies on its own.

## On real AWS, two more layers

- **Block Public Access (BPA).** Four switches, at the account level and per
  bucket, that override any policy or ACL granting public access. With
  account-level BPA on, `"Principal": "*"` simply doesn't take effect. New buckets
  have it on by default since 2023. Turning it **off** is what a "just for the
  demo" change usually involves, so treat that as a change needing review.
- **AWS Config rule** `s3-bucket-level-public-access-prohibited` (or
  `s3-bucket-public-read-prohibited`). It re-checks every bucket continuously and
  flags the one that drifts. That turns "is anything public?" from a one-off audit
  into a standing alarm. Security Hub and IAM Access Analyzer report the same thing.

## Details worth knowing

- **Presigned URLs are bearer tokens.** Anyone who sees the link (an email
  forward, a chat log, a proxy) can use it until it expires. Keep TTLs short
  (minutes to hours). SigV4 caps them at 7 days.
- **A presigned URL can't outlive the credentials that signed it.** If the app
  runs on temporary role credentials, the link dies when they do, often well
  before the TTL. That's a common source of "the partner link expired early" bugs.
- **For a partner relationship**, better than links: give the partner their own
  IAM role or a bucket policy naming *their* account as principal, scoped to a prefix.
- **What this doesn't cover:** data that already leaked. The bucket was public
  for months. On AWS you'd check the S3 server access logs or CloudTrail data
  events to see who downloaded what. That only works if logging was on
  beforehand, and here it wasn't. A real incident also means notifying the
  affected customers.
