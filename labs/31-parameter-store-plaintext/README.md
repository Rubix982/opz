# Lab 31 · Parameter Store Used Insecurely in Plain Text

**Time:** ~45 min · **Needs:** Docker Compose, Python 3 · **Cost:** free, all local (no AWS account)

> **Runs against a local AWS emulator** ([moto](https://github.com/getmoto/moto)),
> not real AWS. The API calls are the same ones you'd make on AWS:
> `put_parameter`, `get_parameters`, `WithDecryption`, KMS keys and aliases. What
> the emulator **can't** prove:
> - **It doesn't enforce IAM or KMS key policies.** On AWS, a role without
>   `kms:Decrypt` on the key is refused when it asks for `WithDecryption=True`.
>   Here every caller can decrypt. That part of the fix is in `SOLUTION.md`, but
>   no local check can test it.
> - **Its "ciphertext" isn't encrypted.** A SecureString read without decryption
>   comes back as `kms:<key>:<value>`. Real AWS returns opaque encrypted bytes.

## The incident

A contractor with read-only access to the AWS console sent a screenshot of
Parameter Store to the wrong Slack channel. The orders database password and the
live payment API key were right there, in plain text. Then the team searched and
found the same two values in a CI log, in `docker inspect` output pasted into a
ticket, and in the app's startup logs in the log platform.

## Setup

```bash
./setup.sh                          # emulator on localhost:9031, bootstrap, app on :8031
curl -s localhost:8031/status       # the app is happy (it shows fingerprints, not values)
docker compose logs app             # ...and what else it says
docker compose config | grep -i -A3 environment
docker inspect opz-lab31-app-1 --format '{{json .Config.Env}}'
```

What the read-only contractor saw:

```bash
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_DEFAULT_REGION=us-east-1 \
  .venv/bin/python -c "import boto3; s=boto3.client('ssm', endpoint_url='http://127.0.0.1:9031'); \
  [print(p['Name'], p['Type'], p['Value']) for p in s.get_parameters_by_path(Path='/orders', Recursive=True)['Parameters']]"
```

`infra/seed.json` stands in for the person who typed the values in once. It's
the only place they're allowed to exist outside Parameter Store.

## Your job

1. **Trace every copy of the two secrets.** List each place they end up and how
   they got there. Hints, one at a time if you're stuck:
   - Read `infra/bootstrap.py` line by line: what does it store, what does it print,
     what does it write?
   - How does the app get its config? Why does that put the values in `docker inspect`?
   - Where does the app's startup log line go after it leaves the container?
2. **Fix it:**
   - The two secrets become `SecureString`s under the team's **own** KMS key
     (create one with an alias, such as `alias/orders-params`). `db_host` isn't secret and can stay a `String`.
   - The app fetches its config from Parameter Store **itself**, at startup, with
     `WithDecryption=True`. The container already has `AWS_ENDPOINT_URL` and
     credentials for the emulator. Nothing secret goes in its environment.
   - Nothing prints or writes the values: not the bootstrap, not the app.
   - Look up `get_parameters` in boto3, and why `.env.app` should stop existing.
3. **Prove it.** `./check.sh` rebuilds everything from your files and looks for
   the values in every place listed above.
4. **Write the retro** (below). **Clean up:** `./teardown.sh`.

Spoilers live in `SOLUTION.md`.

## Retro (fill in)

- Every place the secrets were copied to, and how:
- What `SecureString` changes for someone with read-only access:
- Why the team's own KMS key, not the default `aws/ssm` one:
- What on real AWS would stop the contractor from decrypting (that this emulator can't show):
- What's still exposed: who can still read the values, and from where?
