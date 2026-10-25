# Lab 31 · Solution (spoilers)

## Where the secrets were going

| Copy | How it got there |
|---|---|
| Parameter Store, readable as plain text | `Type="String"`: anyone with `ssm:GetParameter*` or `DescribeParameters` access (the console's read-only view, CI roles) sees the value |
| Bootstrap output (CI logs) | `print(f"put {name} = {value}")` |
| `.env.app` on disk | written by the bootstrap |
| Container environment → `docker inspect`, `docker compose config`, `/proc/1/environ` | `env_file: .env.app` |
| Log platform | the app logs its whole config at startup |

## The fix

**`infra/bootstrap.py`:** a customer-managed key, SecureStrings for the secrets,
no values printed, no `.env.app`:

```python
KEY_ALIAS = "alias/orders-params"
SECRET_NAMES = {"/orders/prod/db_password", "/orders/prod/payment_api_key"}

aliases = {a["AliasName"] for a in kms.list_aliases()["Aliases"]}
if KEY_ALIAS not in aliases:
    key_id = kms.create_key(Description="orders service parameters")["KeyMetadata"]["KeyId"]
    kms.create_alias(AliasName=KEY_ALIAS, TargetKeyId=key_id)

for name, value in seed.items():
    if name in SECRET_NAMES:
        ssm.put_parameter(Name=name, Value=value, Type="SecureString", KeyId=KEY_ALIAS, Overwrite=True)
        print(f"put {name} (SecureString, {KEY_ALIAS})")
    else:
        ssm.put_parameter(Name=name, Value=value, Type="String", Overwrite=True)
        print(f"put {name} (String)")
```

**`app/app.py`:** fetch at startup, decrypt in memory, log names only:

```python
PREFIX = "/orders/prod/"

def load_config() -> dict[str, str]:
    ssm = boto3.client("ssm")
    names = [PREFIX + n for n in ("db_host", "db_password", "payment_api_key")]
    resp = ssm.get_parameters(Names=names, WithDecryption=True)
    if resp["InvalidParameters"]:
        raise SystemExit(f"missing parameters: {resp['InvalidParameters']}")
    return {p["Name"].removeprefix(PREFIX): p["Value"] for p in resp["Parameters"]}

config = load_config()
print(f"starting orders service; loaded {sorted(config)} from {PREFIX}", flush=True)
```

With no `.env.app`, the optional `env_file` in `compose.yaml` adds nothing, so
you can delete it.

## On real AWS, the part the emulator can't show: who may decrypt

`SecureString` only helps if *decrypting* is restricted. Two policies decide that:

- **IAM, on the parameter path.** The app's role gets
  `ssm:GetParameters` on `arn:aws:ssm:<region>:<acct>:parameter/orders/prod/*`
  and nothing else. CI and humans get `ssm:DescribeParameters` at most.
- **The KMS key policy.** Only the app's role gets `kms:Decrypt`, ideally with
  a condition `kms:EncryptionContext:PARAMETER_ARN` matching `/orders/prod/*`.
  A read-only role can see that the parameter *exists*, but
  `GetParameter --with-decryption` fails with `AccessDeniedException`.

That's why the team's own key matters. The AWS-managed `aws/ssm` key can't
have its policy changed, so anyone in the account allowed to read the parameter
can decrypt it. Only a customer-managed key lets you separate "can read" from
"can decrypt". The checklist's "done when" (a role without `kms:Decrypt` is
refused) is exactly this, and on AWS you'd test it with two roles and
`aws ssm get-parameter --with-decryption`. Afterwards, delete the parameters
and schedule the key for deletion (7–30 days' wait). Keys cost about $1 a month.

## Details worth knowing

- **Env vars aren't secret storage** (lab 02's lesson again). They show up in
  `docker inspect`, `/proc/<pid>/environ`, crash reporters and child processes.
  Fetching at runtime keeps the value inside one process's memory.
- **ECS and Lambda can inject SSM parameters as env vars** (`secrets:` in an ECS
  task definition). That's convenient, and the value still lands in the
  environment. Fetching in code is stricter.
- **Secrets Manager vs. Parameter Store.** Secrets Manager adds rotation and
  cross-account sharing, for $0.40 per secret per month. Parameter Store
  SecureStrings are free (standard tier) but have no rotation.
- **Cache, don't spam.** Fetch once at startup, or with a TTL. Parameter Store
  throttles (40 TPS by default), and every decrypt is a billed KMS call.
- **What this doesn't cover:** the values already leaked (the screenshot, the
  logs). They must be **rotated** (lab 03: rotate first), and the old log lines
  purged or access-restricted. Anyone who can run code *as the app* can still
  read the secrets; least privilege on who can deploy or exec into it is the next layer.
