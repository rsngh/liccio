"""Supervised predictors (charter §16.3).

Trains simple scikit-learn models for success / cost / review-burden prediction
from historical (features, outcome) data. Lazy-imports sklearn; falls back to a
mean predictor when unavailable so the module always imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.core.optional import try_import


@dataclass
class TrainResult:
    target: str
    model: Any = None
    n: int = 0
    backend: str = "mean"
    feature_keys: list[str] = field(default_factory=list)
    fallback_mean: float = 0.0


def _vectorize(rows: list[dict[str, Any]], keys: list[str]) -> list[list[float]]:
    out = []
    for r in rows:
        out.append([float(r.get(k, 0) or 0) for k in keys])
    return out


def train_predictor(
    rows: list[dict[str, Any]], target: str, feature_keys: list[str]
) -> TrainResult:
    """Train a regressor/classifier for ``target`` from numeric features."""
    ys = [float(r[target]) for r in rows if target in r]
    if not ys:
        raise ValueError(f"no target values for {target}")
    mean = sum(ys) / len(ys)
    sklearn = try_import("sklearn.linear_model")
    if sklearn is None or len(rows) < 5:
        return TrainResult(target=target, n=len(rows), backend="mean",
                           feature_keys=feature_keys, fallback_mean=mean)
    x = _vectorize(rows, feature_keys)
    model = sklearn.Ridge(alpha=1.0)
    model.fit(x, ys)
    return TrainResult(target=target, model=model, n=len(rows), backend="sklearn",
                       feature_keys=feature_keys, fallback_mean=mean)


def predict(result: TrainResult, features: dict[str, Any]) -> float:
    if result.model is None:
        return result.fallback_mean
    x = _vectorize([features], result.feature_keys)
    return float(result.model.predict(x)[0])
