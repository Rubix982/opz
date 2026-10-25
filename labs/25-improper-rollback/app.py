"""Scoring service. POST /predict with {"x": [600 numbers]} -> {"score": ...}.

The live model is whatever is in models/current/. When the files there change,
the service reloads them, so a deploy or rollback needs no restart.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("PORT", "8025"))
MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).resolve().parent / "models" / "current"))

_lock = threading.Lock()
_model: dict = {}
_mtimes: tuple = ()


def model() -> dict:
    """The current model, reloaded if its files have changed."""
    global _model, _mtimes
    with _lock:
        mtimes = tuple(os.stat(MODEL_DIR / f).st_mtime_ns for f in ("preprocess.json", "weights.json"))
        if mtimes != _mtimes:
            pre = json.loads((MODEL_DIR / "preprocess.json").read_text())
            wts = json.loads((MODEL_DIR / "weights.json").read_text())
            _model, _mtimes = {"pre": pre, "wts": wts}, mtimes
        return _model


def score(m: dict, x: list[float]) -> float:
    pre, wts = m["pre"], m["wts"]
    z = [(xi - mu) / s for xi, mu, s in zip(x, pre["mean"], pre["scale"])]
    return wts["bias"] + sum(c * zi for c, zi in zip(wts["coef"], z))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            x = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))["x"]
            body, code = {"score": round(score(model(), x), 6)}, 200
        except Exception as e:
            body, code = {"error": f"{type(e).__name__}: {e}"}, 500
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print(f"predict {code}", flush=True)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    print(f"scoring service on 127.0.0.1:{PORT}, model from {MODEL_DIR}", flush=True)
    sys.stdout.reconfigure(line_buffering=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
