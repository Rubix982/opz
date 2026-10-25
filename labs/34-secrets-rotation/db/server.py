"""A stand-in for the orders database: it only checks passwords.

    POST /login           {"user": "app", "password": "..."}            -> 200 or 401
    POST /admin/password  {"user": "app", "password": "...", "retain_current": false}
                          header X-Admin-Token                          -> 200
    POST /admin/fault     {"mode": "none" | "down" | "ignore"}          (lab control)

Like MySQL 8, a user can have two valid passwords during a change:
`retain_current: true` keeps the old one working as a secondary password
(MySQL: ALTER USER ... RETAIN CURRENT PASSWORD). The next change drops it.

Faults (for practising failure; they only affect /admin/password):
  down    password changes fail with 503, as if the DB were unreachable
  ignore  password changes answer 200 but don't take effect (a real bug class:
          the change went to a replica, or wasn't committed)
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8034"))
ADMIN_TOKEN = os.environ.get("DB_ADMIN_TOKEN", "admin_FAKE_lab34_do_not_use")
passwords: dict[str, list[str]] = {"app": [os.environ.get("INITIAL_PASSWORD", "pw_FAKE_initial")]}
fault = "none"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        global fault
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        if self.path == "/login":
            ok = body.get("password") in passwords.get(body.get("user", ""), [])
            self._send(200 if ok else 401, {"login": "ok" if ok else "denied"})
        elif self.path == "/admin/password":
            if self.headers.get("X-Admin-Token") != ADMIN_TOKEN:
                self._send(403, {"error": "admin token required"})
            elif fault == "down":
                self._send(503, {"error": "database unreachable"})
            else:
                if fault != "ignore":
                    current = passwords.get(body["user"], [])[:1]
                    passwords[body["user"]] = [body["password"]] + (current if body.get("retain_current") else [])
                self._send(200, {"changed": True})
        elif self.path == "/admin/fault":
            fault = body.get("mode", "none")
            self._send(200, {"fault": fault})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)


if __name__ == "__main__":
    print(f"database on 127.0.0.1:{PORT}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
