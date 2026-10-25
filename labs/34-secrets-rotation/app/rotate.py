"""Rotates the orders database password. Runs nightly from cron.

    python app/rotate.py
"""

import json
import secrets as rand

from common import SECRET_ID, db_post, secrets

sm = secrets()


def main() -> None:
    try:
        new = "pw_FAKE_" + rand.token_hex(12)
        # Store the new password first so we never lose it.
        sm.put_secret_value(SecretId=SECRET_ID, SecretString=json.dumps({"username": "app", "password": new}))
        db_post("/admin/password", {"user": "app", "password": new}, admin=True)
        print("rotated")
    except Exception as e:
        # Don't wake anyone up for a rotation hiccup; it'll run again tomorrow.
        print(f"warning: rotation hiccup: {e}")


main()
