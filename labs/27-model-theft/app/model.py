"""The credit-decision model and its (synthetic) data.

Trained at startup from a fixed seed, so every run gets the same model. The
model took the team months of feature work, and it's the product.
"""

import numpy as np
from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ["age", "years_at_address", "monthly_income_usd", "open_loans",
            "credit_history_months", "late_payments", "utilisation_score", "account_age_months"]
CLASSES = ["approve", "review", "decline"]

_SCALE = np.array([3, 1, 50, 0.5, 10, 2, 1, 8])
_SHIFT = np.array([40, 0, 600, 1, 100, 5, 0, 30])


def _data() -> tuple[np.ndarray, np.ndarray]:
    X, y = make_classification(n_samples=6000, n_features=8, n_informative=5, n_redundant=1,
                               n_classes=3, n_clusters_per_class=1, class_sep=1.0, random_state=27)
    return X * _SCALE + _SHIFT, y


def train() -> tuple[Pipeline, np.ndarray, np.ndarray]:
    """Returns the model, the training inputs and a held-out set of real customers."""
    X, y = _data()
    X_train, X_test, y_train, _ = train_test_split(X, y, test_size=0.3, random_state=0)
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X_train, y_train)
    return model, X_train, X_test


def published_ranges() -> list[tuple[float, float]]:
    """The valid range of each feature, as printed in the public API docs."""
    X, _ = _data()
    return [(float(lo), float(hi)) for lo, hi in zip(X.min(0), X.max(0))]


def real_customers(n: int, seed: int = 0) -> np.ndarray:
    """A sample of genuine applications (what honest API clients send)."""
    _, _, X_test = train()
    rng = np.random.default_rng(seed)
    return X_test[rng.choice(len(X_test), size=n, replace=False)]
