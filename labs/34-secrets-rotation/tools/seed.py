"""Creates the secret with the database's initial password. ./setup.sh runs this."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from common import SECRET_ID, secrets  # noqa: E402

sm = secrets()
try:
    sm.delete_secret(SecretId=SECRET_ID, ForceDeleteWithoutRecovery=True)
except sm.exceptions.ResourceNotFoundException:
    pass
sm.create_secret(Name=SECRET_ID, SecretString=json.dumps({"username": "app", "password": "pw_FAKE_initial"}))
print(f"created secret {SECRET_ID}")
