"""Rotates a client's API key.

    python app/rotate.py billing

Runbook step from the security review: "keys older than 90 days must be rotated".
"""

import secrets
import sys
import time

from common import apigw, keys_for, plan_id

client = sys.argv[1]
ag = apigw()
plan = plan_id(ag)

# out with the old...
for old in keys_for(ag, client):
    ag.delete_usage_plan_key(usagePlanId=plan, keyId=old["id"])
    ag.delete_api_key(apiKey=old["id"])
    print(f"deleted old key {old['id']} ({old['name']})")

# ...in with the new
value = f"FAKE-{client}-{secrets.token_hex(10)}"
new = ag.create_api_key(
    name=f"{client}-{time.strftime('%Y%m%d%H%M%S')}", enabled=True, value=value, tags={"client": client}
)
ag.create_usage_plan_key(usagePlanId=plan, keyId=new["id"], keyType="API_KEY")
print(f"new key {new['id']} for {client}: {value}")
print(f"Paste it into the {client} service's config and redeploy it.")
