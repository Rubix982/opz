# Lab 27 · Solution (spoilers)

## Why it was so easy

The API returned the model's probability for every class. For a logistic model,
`log(p_review / p_approve)` is exactly a linear function of the input, so every
answer is a linear equation in the model's weights. With 8 features, about 9
answers per class pair pin the weights down. `extract.py` "steals" the model by
solving a least-squares problem, and gets a 98% match.

Take the probabilities away and it trains a classifier on the decisions instead:

| Answers the attacker gets | Copy agreement (decisions only) |
|---|---|
| 3,000 | ~98% |
| 1,000 | ~98% |
| 300 | ~91% |
| ~20 | ~55% |

So labels-only removes the exact attack, but a simple model is still cheap to
copy from labels. Volume is what has to be cut.

## The fix: three layers

```python
DAILY_BUDGET = 1000              # per key; biggest customer needs ~500 at month end
SWEEP_MIN_QUERIES = 20           # judge a key only after this many queries
SWEEP_MAX_ODD_FRACTION = 0.5     # real applicants look like real applicants
P1, P99 = np.percentile(X_TRAIN, [1, 99], axis=0)
```

1. **Return the decision only:** `{"decision": "approve"}`. If clients need a
   score, return one coarse value (a 1–5 band), never a vector of probabilities.
2. **A per-key daily budget** (429 with a reason when exceeded). Sized from real
   usage: here 1,000, about twice the biggest customer's month-end peak.
3. **Sweep detection.** A query is *odd* if any feature lies outside the 1st–99th
   percentile of the training data. Real applications are odd ~15% of the time;
   uniform sweeps over the published ranges almost always. Once a key has sent
   20 queries, more than half of them odd means suspend it (403) and raise an
   alert for a human to review.

```python
def admit(key, features):
    odd = bool(np.any((np.array(features) < P1) | (np.array(features) > P99)))
    with lock:
        if key in blocked:
            return 403, "key suspended pending review"
        u = usage.setdefault(key, {"day": today(), "count": 0, "odd": 0, "total": 0})
        ...                                  # reset count when the day changes
        if u["count"] >= DAILY_BUDGET:
            return 429, f"daily budget of {DAILY_BUDGET} reached"
        u["count"] += 1; u["total"] += 1; u["odd"] += odd
        if u["total"] >= SWEEP_MIN_QUERIES and u["odd"] / u["total"] > SWEEP_MAX_ODD_FRACTION:
            blocked.add(key)
            log.warning("ALERT: %s suspended, %d/%d queries off the data distribution", ...)
            return 403, "key suspended pending review"
    return None
```

`check.sh`: honest 200/200, no probabilities, bulk partner cut off at 1,000,
attacker suspended after 19 answers with a 56% copy. Budget without detection
fails: 1,000 answers still make a 98% copy.

## Details worth knowing

- **Each layer covers a different attacker.** Labels-only stops the cheap exact
  attack. The budget caps any single key. Detection catches a key that is
  plainly not scoring customers.
- **How attackers adapt:** many keys (free trials, fake companies): tie trials to
  identity checks and a payment method, and budget per *organisation*. Realistic
  queries: an attacker with even a little real data can sample near it and stay
  under the detector, so the budget is the backstop. **Active learning**: querying
  near the decision boundary needs far fewer labels than random sweeps.
- **Watermarking** doesn't prevent theft; it lets you prove it later. You
  deliberately answer a secret set of unusual "canary" inputs in a distinctive
  way. If a competitor's model reproduces your canary answers, that's evidence
  it was trained on your outputs.
- **Contracts and monitoring are part of the defence.** Terms of service that
  forbid training on outputs, and per-key usage dashboards. Most real extraction
  is spotted by a human looking at a usage graph.
- **What this doesn't cover:** insiders exporting the weights, or stolen model files.
  That's access control on the artifact itself (the C2 scenarios in the checklist).
