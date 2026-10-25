"""Tiny client used by the other tools."""

import json
import urllib.error
import urllib.request

import os

URL = os.environ.get("API_URL", "http://127.0.0.1:8027")


def score(key: str, features: list[float]) -> tuple[int, dict]:
    req = urllib.request.Request(f"{URL}/score", data=json.dumps({"features": features}).encode(),
                                 method="POST", headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, {}
