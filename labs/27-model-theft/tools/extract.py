"""The attack: steal a working copy of the model through the API.

    python tools/extract.py [--key key_FAKE_rival] [--budget 3000]

Like a real attacker, it has no training data. It reads the feature ranges from
the public docs, sends random applications across those ranges, and trains its
own model on the answers:

- If the API returns per-class probabilities, the log-odds of a logistic model
  are a linear function of the inputs, so it solves for the weights directly.
- If it only gets decisions, it trains a classifier on the decisions.
- When the API refuses it (403/429), it stops and works with what it has.

Then, as the defender, we measure the copy: how often does it agree with the
real model on genuine applications it never saw?
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from client import score  # noqa: E402
from model import CLASSES, published_ranges, real_customers, train  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--key", default="key_FAKE_rival")
p.add_argument("--budget", type=int, default=3000)
p.add_argument("--seed", type=int, default=7)
a = p.parse_args()

rng = np.random.default_rng(a.seed)
lo, hi = np.array(published_ranges()).T
queries, labels, probs = [], [], []
refused = None
for i in range(a.budget):
    x = rng.uniform(lo, hi)
    code, body = score(a.key, [float(v) for v in x])
    if code != 200:
        refused = {"after": i, "status": code}
        break
    queries.append(x)
    labels.append(CLASSES.index(body["decision"]))
    pr = body.get("probabilities")
    probs.append([pr[c] for c in CLASSES] if isinstance(pr, dict) else None)

Q, y = np.array(queries), np.array(labels)
method = "none"
copy_predict = None
if len(Q) and all(p is not None for p in probs):
    P = np.clip(np.array(probs), 1e-12, 1)
    reg = LinearRegression().fit(Q, np.log(P[:, 1:] / P[:, [0]]))
    copy_predict = lambda X: np.c_[np.zeros(len(X)), reg.predict(X)].argmax(1)
    method = "solved from probabilities"
elif len(set(labels)) >= 2:
    clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000)).fit(Q, y)
    copy_predict = clf.predict
    method = "trained on decisions"

victim, _, _ = train()
test = real_customers(1500, seed=99)
truth = victim.predict(test)
if copy_predict is None:  # too little to train on: the best guess is the most common answer seen
    guess = np.bincount(y, minlength=len(CLASSES)).argmax() if len(y) else 0
    agreement = float((truth == guess).mean())
    method = "majority guess (too few answers)"
else:
    agreement = float((copy_predict(test) == truth).mean())

print(json.dumps({"answered": len(Q), "refused": refused, "method": method,
                  "agreement": round(agreement, 3)}))
