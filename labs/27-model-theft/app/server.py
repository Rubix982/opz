"""Credit-decision API, sold per seat to lenders.

    POST /score   body {"features": [8 numbers]}, header X-API-Key
                  -> the decision, plus the model's probability for each class

Keys live in app/keys.json.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from model import CLASSES, FEATURES, train

PORT = int(os.environ.get("PORT", "8027"))
KEYS = json.loads((Path(__file__).parent / "keys.json").read_text())
MODEL, X_TRAIN, _ = train()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path != "/score":
            self._send(404, {"error": "not found"})
            return
        key = self.headers.get("X-API-Key", "")
        if key not in KEYS:
            self._send(401, {"error": "unknown API key"})
            return
        try:
            features = [float(v) for v in json.loads(raw)["features"]]
            assert len(features) == len(FEATURES)
        except Exception:
            self._send(400, {"error": f"send {{'features': [{len(FEATURES)} numbers]}} in this order: {FEATURES}"})
            return

        probs = MODEL.predict_proba([features])[0]
        self._send(200, {
            "decision": CLASSES[int(probs.argmax())],
            "probabilities": {c: float(p) for c, p in zip(CLASSES, probs)},
        })

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    print(f"credit API on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
