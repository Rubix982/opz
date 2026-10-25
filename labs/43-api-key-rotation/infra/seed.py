"""Creates the API, the usage plan and one API key per client service, and hands
each client its key by writing keys/<client>.key (our stand-in for a secret store).
"""

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from common import CLIENTS, KEYS_DIR, PLAN_NAME, apigw  # noqa: E402

ag = apigw()
ag.create_rest_api(name="orders-api")
plan = ag.create_usage_plan(name=PLAN_NAME)
KEYS_DIR.mkdir(exist_ok=True)
for client in CLIENTS:
    value = f"FAKE-{client}-{secrets.token_hex(10)}"
    key = ag.create_api_key(name=f"{client}-2026-09", enabled=True, value=value, tags={"client": client})
    ag.create_usage_plan_key(usagePlanId=plan["id"], keyId=key["id"], keyType="API_KEY")
    (KEYS_DIR / f"{client}.key").write_text(value + "\n")
    print(f"{client:8} key {key['id']} -> {KEYS_DIR / (client + '.key')}")
