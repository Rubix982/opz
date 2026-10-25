"""The orders app's database login: fetch the current secret, connect.

    python app/app.py      # exit 0 and "app: connected" if it works
"""

import json
import sys

from common import SECRET_ID, can_login, secrets

# Ask for AWSCURRENT by name. (Real AWS defaults to it; the emulator needs it spelled out.)
secret = json.loads(secrets().get_secret_value(SecretId=SECRET_ID, VersionStage="AWSCURRENT")["SecretString"])
if can_login(secret["password"]):
    print("app: connected")
else:
    print("app: login FAILED with the current secret", file=sys.stderr)
    sys.exit(1)
