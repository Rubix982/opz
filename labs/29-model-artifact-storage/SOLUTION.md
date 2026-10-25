# Lab 29 · Solution (spoilers)

## What was wrong

| Problem | Effect |
|---|---|
| `mc anonymous set download` | Anyone who can reach the store, or finds a URL, can download every checkpoint |
| One admin login everywhere | Any service, or any leak of its config, can delete or replace everything. Logs can't tell who did what |
| No versioning | An overwrite destroys the previous weights for good |
| No integrity check | The server loads whatever bytes are in the bucket |
| No audit trail | "Who downloaded it?" has no answer |

## The fix

**`infra/init.sh`:**

```bash
envval() { sed -n "s/^$2=//p" "/config/$1.env"; }
...
mc anonymous set none local/models
mc version enable local/models

cat > /tmp/models-read.json <<'J'
{"Version": "2012-10-17", "Statement": [
  {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
   "Resource": ["arn:aws:s3:::models", "arn:aws:s3:::models/*"]}]}
J
cat > /tmp/models-publish.json <<'J'
{"Version": "2012-10-17", "Statement": [
  {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
   "Resource": ["arn:aws:s3:::models", "arn:aws:s3:::models/*"]}]}
J
mc admin policy create local models-read /tmp/models-read.json
mc admin policy create local models-publish /tmp/models-publish.json
mc admin user add local "$(envval server S3_ACCESS_KEY)" "$(envval server S3_SECRET_KEY)"
mc admin user add local "$(envval trainer S3_ACCESS_KEY)" "$(envval trainer S3_SECRET_KEY)"
mc admin policy attach local models-read --user "$(envval server S3_ACCESS_KEY)" || true
mc admin policy attach local models-publish --user "$(envval trainer S3_ACCESS_KEY)" || true
```

(`|| true` because attaching an already-attached policy is an error on re-runs.)

**`config/server.env` and `config/trainer.env`:** each gets its own login,
for example `inference-FAKE` / `trainer-FAKE`, with its own secret.

**`compose.yaml`**, on the `s3` service:

```yaml
      MINIO_AUDIT_WEBHOOK_ENABLE_collector: "on"
      MINIO_AUDIT_WEBHOOK_ENDPOINT_collector: http://audit:8080/
```

**Integrity: a registry outside the bucket.** The trainer records each model's
SHA-256 in `registry.json`, which lives in git and is reviewed like code. The
server refuses anything that doesn't match:

```python
# train.py
    data = weights.read_bytes()
    s3.put_object(Bucket=BUCKET, Key=model_key(name), Body=data)
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    registry[name] = hashlib.sha256(data).hexdigest()
    REGISTRY.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")

# serve.py
    weights = s3.get_object(Bucket=BUCKET, Key=model_key(name))["Body"].read()
    expected = json.loads(REGISTRY.read_text()).get(name) if REGISTRY.exists() else None
    actual = hashlib.sha256(weights).hexdigest()
    if expected is None:
        raise TamperedModel(f"{name} isn't in the registry; refusing to load an unknown model")
    if actual != expected:
        raise TamperedModel(f"{name}: sha256 {actual} doesn't match the registry's {expected}")
```

After this, the seeded `sentiment/v3` won't load, because it was never
registered. That's correct behaviour. Publish it through `train.py` to register it.

## Details worth knowing

- **Why not store the checksum next to the weights** (object metadata or a
  `model.sha256` file)? Whoever can replace the weights can replace the checksum
  in the same request. The check only works if the expected value lives somewhere
  that writer can't touch: git, a model registry (MLflow), or a signature
  (lab *Unsigned Model Artifacts*, Cosign). Signatures are the grown-up version:
  the server holds only a public key, and only the signing key can bless a model.
- **Versioning costs storage.** Every overwrite keeps the old bytes. Add a
  lifecycle rule that expires *noncurrent* versions after N days. For models that
  must never change, **object lock** (WORM) prevents deletion even by admins for
  a retention period. It must be enabled when the bucket is created.
- **A deleted object isn't gone either.** On a versioned bucket a delete just
  adds a "delete marker". That's why the trainer still doesn't get `s3:DeleteObject`.
- **Audit logs answer "who", but only from now on.** The leaked checkpoint's
  download is unrecoverable. Ship audit logs somewhere the admin login can't edit.
- **What this doesn't cover:** encryption at rest (MinIO SSE with a KMS, S3
  SSE-KMS), TLS on the wire (this store is plain HTTP), and rotating the logins
  (lab 10). The admin login still exists. Keep it out of every service and
  behind MFA, and use it rarely enough that each use shows up in the audit log.
- **On AWS** the same design is: bucket with Block Public Access, one IAM role
  per service (no long-lived keys at all), versioning plus lifecycle rules,
  CloudTrail S3 *data events* for the audit trail, and SageMaker Model Registry
  or signatures for integrity.
