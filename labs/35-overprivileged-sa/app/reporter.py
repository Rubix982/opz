"""Reporter: reads its settings from the ConfigMap "reporter-config" through the
Kubernetes API, using the pod's own service account token, and serves a status page.

    GET /status   when the config was last read, and what it said
    GET /healthz  liveness
"""

import json
import ssl
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SA = "/var/run/secrets/kubernetes.io/serviceaccount"
API = "https://kubernetes.default.svc"
state: dict = {"ok": False, "last_read": None, "config": None, "error": None}


def api_get(path: str) -> dict:
    token = open(f"{SA}/token").read().strip()
    ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
        return json.load(resp)


def refresh_loop() -> None:
    namespace = open(f"{SA}/namespace").read().strip()
    while True:
        try:
            cm = api_get(f"/api/v1/namespaces/{namespace}/configmaps/reporter-config")
            state.update(ok=True, last_read=time.time(), config=cm.get("data"), error=None)
        except Exception as e:  # keep serving; report the problem on /status
            state.update(ok=False, error=str(e))
            print(f"config read failed: {e}", flush=True)
        time.sleep(3)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            body, code = {"ok": True}, 200
        elif self.path == "/status":
            age = time.time() - state["last_read"] if state["last_read"] else None
            body = {**state, "seconds_since_read": round(age, 1) if age is not None else None}
            code = 200
        else:
            body, code = {"error": "not found"}, 404
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    threading.Thread(target=refresh_loop, daemon=True).start()
    print("reporter on :8080", flush=True)
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
