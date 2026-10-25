"""What can this pod's token do? Read-only probes against the Kubernetes API,
using the service account token mounted in the pod (the way an attacker who
found a bug in the app would).

    kubectl exec deploy/reporter -n shop -- python /app/peek.py          # human-readable
    kubectl exec deploy/reporter -n shop -- python /app/peek.py --json   # for check.sh

Only GET requests. Nothing is created, changed or deleted.
"""

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

SA = "/var/run/secrets/kubernetes.io/serviceaccount"
API = "https://kubernetes.default.svc"

PROBES = [
    ("own ConfigMap (the app's real job)", "/api/v1/namespaces/shop/configmaps/reporter-config"),
    ("list Secrets in shop", "/api/v1/namespaces/shop/secrets"),
    ("read a Secret in billing", "/api/v1/namespaces/billing/secrets/db-password"),
    ("list namespaces (cluster-wide)", "/api/v1/namespaces"),
    ("list pods in every namespace", "/api/v1/pods"),
]


def get(path: str, token: str) -> tuple[int, dict | None]:
    ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(10):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            return e.code, None
        except urllib.error.URLError:  # cluster DNS still starting: try again shortly
            time.sleep(1)
    return 0, None


def main() -> None:
    as_json = "--json" in sys.argv
    if not os.path.exists(f"{SA}/token"):
        print(json.dumps({"token": False}) if as_json else "no service account token mounted in this pod")
        return
    token = open(f"{SA}/token").read().strip()
    results = []
    for name, path in PROBES:
        code, body = get(path, token)
        results.append({"probe": name, "path": path, "status": code})
        if as_json:
            continue
        verdict = "ALLOWED" if code == 200 else f"denied ({code})"
        print(f"{verdict:12} {name}")
        if code == 200 and body and body.get("kind") == "SecretList":
            for item in body.get("items", [])[:5]:
                values = {k: base64.b64decode(v).decode(errors="replace") for k, v in (item.get("data") or {}).items()}
                print(f"             - {item['metadata']['name']}: {values}")
        if code == 200 and body and body.get("kind") == "Secret":
            values = {k: base64.b64decode(v).decode(errors="replace") for k, v in (body.get("data") or {}).items()}
            print(f"             - {body['metadata']['name']}: {values}")
    if as_json:
        print(json.dumps({"token": True, "results": results}))


if __name__ == "__main__":
    main()
