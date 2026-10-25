"""Customer export service.

    POST /exports/<name>        body = CSV; stores it as 2026/<name>.csv
    GET  /exports/<name>        the CSV (read with the service's own credentials)
    GET  /exports/<name>/share  a link to hand to a partner, as {"url": ...}

Settings (environment):
    S3_ENDPOINT          where S3 is (default http://127.0.0.1:9030, the local MinIO)
    SHARE_TTL_SECONDS    how long a partner link may work (default 900)
    PORT                 default 8030
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def _dotenv() -> dict[str, str]:
    env = Path(__file__).resolve().parent.parent / ".env"
    pairs = (line.split("=", 1) for line in env.read_text().splitlines() if "=" in line and not line.startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


ENDPOINT = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:9030")
BUCKET = "acme-customer-exports"
SHARE_TTL_SECONDS = int(os.environ.get("SHARE_TTL_SECONDS", "900"))
PORT = int(os.environ.get("PORT", "8030"))
_creds = _dotenv()

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=_creds["MINIO_ROOT_USER"],
    aws_secret_access_key=_creds["MINIO_ROOT_PASSWORD"],
    region_name="us-east-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)


def key_for(name: str) -> str:
    return f"2026/{name}.csv"


def share_link(name: str) -> str:
    # The bucket is public, so a plain URL is all the partner needs.
    # TODO: links never expire; SHARE_TTL_SECONDS isn't used yet.
    return f"{ENDPOINT}/{BUCKET}/{key_for(name)}"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _name(self) -> str | None:
        m = re.fullmatch(r"/exports/([a-z0-9-]+)(/share)?", self.path)
        return m.group(1) if m else None

    def do_POST(self) -> None:
        name = self._name()
        if not name or self.path.endswith("/share"):
            self._send(404, b'{"error": "not found"}')
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        s3.put_object(Bucket=BUCKET, Key=key_for(name), Body=body, ContentType="text/csv")
        self._send(201, json.dumps({"stored": key_for(name)}).encode())

    def do_GET(self) -> None:
        name = self._name()
        if not name:
            self._send(404, b'{"error": "not found"}')
            return
        if self.path.endswith("/share"):
            self._send(200, json.dumps({"url": share_link(name), "ttl_seconds": SHARE_TTL_SECONDS}).encode())
            return
        try:
            obj = s3.get_object(Bucket=BUCKET, Key=key_for(name))
        except ClientError as e:
            self._send(404, json.dumps({"error": str(e)}).encode())
            return
        self._send(200, obj["Body"].read(), "text/csv")

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)


if __name__ == "__main__":
    print(f"exports service on 127.0.0.1:{PORT}, S3 at {ENDPOINT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
