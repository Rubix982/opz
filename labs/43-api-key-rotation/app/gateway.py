"""The API gateway in front of the orders API.

    GET /orders   needs header x-api-key: <a key on the "partners" usage plan>
    GET /stats    request counts

Valid keys are looked up from API Gateway (the emulator) and cached for
CACHE_TTL seconds, like any gateway that doesn't call its control plane on
every request.
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import apigw, plan_id

PORT = int(os.environ.get("PORT", "8043"))
CACHE_TTL = float(os.environ.get("CACHE_TTL", "3"))

ag = apigw()
lock = threading.Lock()
cache: dict = {"at": 0.0, "keys": {}}  # key value -> (key id, key name)
stats = {"ok": 0, "denied": 0}


def valid_keys() -> dict:
    with lock:
        if time.time() - cache["at"] > CACHE_TTL:
            plan = plan_id(ag)
            on_plan = {k["id"] for k in ag.get_usage_plan_keys(usagePlanId=plan)["items"]}
            cache["keys"] = {
                k["value"]: (k["id"], k["name"])
                for k in ag.get_api_keys(includeValues=True)["items"]
                if k["enabled"] and k["id"] in on_plan
            }
            cache["at"] = time.time()
        return cache["keys"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/stats":
            self._send(200, stats)
            return
        if self.path != "/orders":
            self._send(404, {"error": "not found"})
            return
        key = valid_keys().get(self.headers.get("x-api-key", ""))
        if key is None:
            with lock:
                stats["denied"] += 1
            self._send(403, {"message": "Forbidden"})
            return
        with lock:
            stats["ok"] += 1
        self._send(200, {"orders": ["ord_1001", "ord_1002"]})

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    print(f"gateway on 127.0.0.1:{PORT}, key cache {CACHE_TTL}s", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
