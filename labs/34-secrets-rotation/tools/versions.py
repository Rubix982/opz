"""Shows every version of the secret and its staging labels."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from common import SECRET_ID, can_login, secrets  # noqa: E402

sm = secrets()
for v in sm.list_secret_version_ids(SecretId=SECRET_ID, IncludeDeprecated=True)["Versions"]:
    pw = json.loads(sm.get_secret_value(SecretId=SECRET_ID, VersionId=v["VersionId"])["SecretString"])["password"]
    print(f"{v['VersionId'][:8]}  {', '.join(v.get('VersionStages', [])) or '(no label)':28}  "
          f"{pw[:16]}…  db login: {'ok' if can_login(pw) else 'denied'}")
