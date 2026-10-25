"""An honest customer: scores N real applications and checks every decision.

    python tools/honest_client.py [--key key_FAKE_acme] [--n 200]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from client import score  # noqa: E402
from model import CLASSES, real_customers, train  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--key", default="key_FAKE_acme")
p.add_argument("--n", type=int, default=200)
p.add_argument("--seed", type=int, default=1)
a = p.parse_args()

model, _, _ = train()
customers = real_customers(a.n, seed=a.seed)
expected = [CLASSES[i] for i in model.predict(customers)]
served = correct = 0
first_refusal = None
example = None
for i, (x, want) in enumerate(zip(customers, expected)):
    code, body = score(a.key, [float(v) for v in x])
    if code == 200:
        served += 1
        correct += body.get("decision") == want
        example = example or body
    elif first_refusal is None:
        first_refusal = {"at": i, "status": code, "body": body}
print(json.dumps({"key": a.key, "sent": a.n, "served": served, "correct": correct,
                  "first_refusal": first_refusal, "example_response": example}))
