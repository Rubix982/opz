"""Orders service. Needs the database password and the payment API key.

    GET /status   whether the config loaded, with fingerprints (not values) of the secrets
"""

import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


def load_config() -> dict[str, str]:
    return {
        "db_host": os.environ["DB_HOST"],
        "db_password": os.environ["DB_PASSWORD"],
        "payment_api_key": os.environ["PAYMENT_API_KEY"],
    }


config = load_config()
print(f"starting orders service with config {config}", flush=True)


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/status":
            self.send_error(404)
            return
        body = json.dumps({
            "db_host": config["db_host"],
            "db_password_fingerprint": fingerprint(config["db_password"]),
            "payment_api_key_fingerprint": fingerprint(config["payment_api_key"]),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8031), Handler).serve_forever()
