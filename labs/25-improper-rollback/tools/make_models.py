"""Writes models/v1 and models/v2 (given; already run). Each version is two files
that only work together: preprocess.json (how to scale the inputs) and
weights.json (the linear model trained on inputs scaled that way)."""

import json
import random
from pathlib import Path

DIM = 600
root = Path(__file__).resolve().parent.parent / "models"
for version, seed in (("v1", 1), ("v2", 2)):
    rng = random.Random(seed)
    d = root / version
    d.mkdir(parents=True, exist_ok=True)
    pre = {"version": version, "mean": [rng.uniform(-1, 1) for _ in range(DIM)],
           "scale": [rng.uniform(0.5, 2.0) for _ in range(DIM)]}
    wts = {"version": version, "bias": rng.uniform(-1, 1), "coef": [rng.uniform(-1, 1) for _ in range(DIM)]}
    (d / "preprocess.json").write_text(json.dumps(pre, indent=1))
    (d / "weights.json").write_text(json.dumps(wts, indent=1))
