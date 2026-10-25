"""Copies a version's files over models/current/, one file at a time.

Model files are large in real life, so each is written in chunks; this one
simulates that with a short pause per chunk.
"""

import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent / "models"
src, dst = root / sys.argv[1], root / "current"
dst.mkdir(exist_ok=True)
for name in ("weights.json", "preprocess.json"):
    data = (src / name).read_bytes()
    with open(dst / name, "wb") as f:
        for i in range(0, len(data), len(data) // 10 + 1):
            f.write(data[i:i + len(data) // 10 + 1])
            f.flush()
            time.sleep(0.03)
print(f"copied {sys.argv[1]} into models/current")
