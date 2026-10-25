"""Receives MinIO audit events (HTTP POSTs of JSON) and appends them to /audit/audit.log.

Stands in for whatever ships audit logs in real life (CloudTrail, a SIEM, Loki).
"""

from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        with open("/audit/audit.log", "ab") as f:
            f.write(body.strip() + b"\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
