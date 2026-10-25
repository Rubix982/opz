"""Fits the house-price model and prints its weights.

The numbers this prints for the reference data are the ones in the paper's
Table 2 (app/expected.json). Any environment that runs this must reproduce them.
"""

import csv
import json
from pathlib import Path

from featurekit import standardize

ROWS = list(csv.DictReader(open(Path(__file__).parent / "data" / "houses.csv")))
FEATURES = ["sqft", "bedrooms", "age_years"]


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination for the normal equations (small, so no numpy)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


columns = [standardize([float(r[f]) for r in ROWS]) for f in FEATURES]
X = [[1.0] + [col[i] for col in columns] for i in range(len(ROWS))]
y = [float(r["price_k"]) for r in ROWS]
XtX = [[sum(X[k][i] * X[k][j] for k in range(len(X))) for j in range(4)] for i in range(4)]
Xty = [sum(X[k][i] * y[k] for k in range(len(X))) for i in range(4)]
w = solve(XtX, Xty)
rmse = (sum((sum(wi * xi for wi, xi in zip(w, x)) - t) ** 2 for x, t in zip(X, y)) / len(y)) ** 0.5
print(json.dumps({"intercept": round(w[0], 4), "weights": dict(zip(FEATURES, (round(v, 4) for v in w[1:]))),
                  "rmse": round(rmse, 4)}))
