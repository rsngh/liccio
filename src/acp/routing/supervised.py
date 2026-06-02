"""Supervised predictors (charter §16.3).

Trains simple scikit-learn models for success / cost / review-burden prediction
from historical (features, outcome) data. Lazy-imports sklearn; falls back to a
mean predictor when unavailable so the module always imports.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from acp.core.enums import ExplorationMode
from acp.core.optional import try_import
from acp.routing.features import RoutingFeatureExtractor
from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction


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


# --------------------------------------------------------------------------
# Supervised meta-router (Alpha 6, WS4)
# --------------------------------------------------------------------------


def featurize(context_key: str, action_key: str) -> dict[str, float]:
    """Bag-of-tokens features over the context and action keys.

    Unlike the tabular bandit (one arm per exact (ctx, action) pair), this lets a
    linear model *generalize*: it learns that "agent=claude_harness" or
    "strategy=test_focused" or "task_type=bugfix" is good in general, so it can
    score a (ctx, action) combination it has never seen verbatim.
    """
    feats: dict[str, float] = {}
    for tok in context_key.split("|"):
        if tok:
            feats[f"ctx={tok}"] = 1.0
    for tok in action_key.split("|"):
        if tok and tok != "-":
            feats[f"act={tok}"] = 1.0
    return feats


@dataclass
class SupervisedRoutingPolicy:
    """A routing policy that scores candidates with a learned reward predictor.

    Cold-start (no training rows) routes uniformly at random so it still produces
    valid propensities; once :meth:`fit` has data it scores each candidate's
    predicted reward (minus a cost penalty) and exploits the best, with optional
    epsilon exploration. Implements the ``RoutingPolicy`` protocol.
    """

    policy_version: str = "supervised-v1"
    epsilon: float = 0.0
    cost_weight: float = 0.0
    temperature: float = 0.0  # >0 => softmax propensities instead of greedy
    seed: int = 1234
    _model: TrainResult | None = None
    _feature_keys: list[str] = field(default_factory=list)
    _rows: list[dict[str, Any]] = field(default_factory=list)
    _rng: random.Random = field(default_factory=lambda: random.Random(1234))

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    # ---- training -------------------------------------------------------
    def fit(self, rows: list[dict[str, Any]]) -> None:
        """Train from rows of ``{context_key, action_key, reward}``."""
        feats_rows: list[dict[str, Any]] = []
        keys: set[str] = set()
        for r in rows:
            f = featurize(r["context_key"], r["action_key"])
            f["reward"] = float(r["reward"])
            keys.update(k for k in f if k != "reward")
            feats_rows.append(f)
        self._rows = list(rows)
        self._feature_keys = sorted(keys)
        if feats_rows:
            self._model = train_predictor(feats_rows, "reward", self._feature_keys)

    def predicted_reward(self, context_key: str, action_key: str) -> float:
        if self._model is None:
            return 0.0
        return predict(self._model, featurize(context_key, action_key))

    # ---- distribution / OPE target -------------------------------------
    def action_distribution(
        self, context_key: str, candidate_keys: list[str]
    ) -> dict[str, float]:
        """pi(action | context) over the candidate set."""
        n = len(candidate_keys)
        if n == 0:
            return {}
        if self._model is None:
            return dict.fromkeys(candidate_keys, 1.0 / n)
        scores = {k: self.predicted_reward(context_key, k) for k in candidate_keys}
        if self.temperature > 0:
            mx = max(scores.values())
            exps = {k: math.exp((v - mx) / self.temperature) for k, v in scores.items()}
            z = sum(exps.values()) or 1.0
            dist = {k: v / z for k, v in exps.items()}
        else:
            best = max(scores.values())
            winners = [k for k, v in scores.items() if v == best]
            dist = {k: ((1 - self.epsilon) / len(winners) if k in winners else 0.0)
                    + self.epsilon / n for k in candidate_keys}
        return dist

    def as_target(self):
        """Adapt to an OPE ``TargetPolicy`` ``(ctx, action, candidates) -> prob``."""
        def pi(ctx: str, action: str, cands: list[str]) -> float:
            return self.action_distribution(ctx, cands).get(action, 0.0)
        return pi

    # ---- RoutingPolicy protocol ----------------------------------------
    def choose_action(
        self, features: dict, candidates: list[RoutingAction]
    ) -> PolicyDecision:
        ctx = RoutingFeatureExtractor.context_key(features)  # type: ignore[arg-type]
        keys = [a.key() for a in candidates]
        dist = self.action_distribution(ctx, keys)
        scores = {k: self.predicted_reward(ctx, k) for k in keys}
        if self.cost_weight:
            for a in candidates:
                scores[a.key()] -= self.cost_weight * a.max_cost_usd
        # Sample from the distribution (deterministic given the seed).
        r = self._rng.random()
        cum = 0.0
        chosen = candidates[-1]
        for a in candidates:
            cum += dist.get(a.key(), 0.0)
            if r <= cum:
                chosen = a
                break
        explored = self._model is None or self.epsilon > 0 or self.temperature > 0
        return PolicyDecision(
            policy_version=self.policy_version,
            action=chosen,
            action_probability=max(1e-6, min(1.0, dist.get(chosen.key(), 1.0 / len(keys)))),
            context_key=ctx,
            candidate_scores=scores,
            exploration_mode=ExplorationMode.EXPLORE if explored else ExplorationMode.EXPLOIT,
            exploration_reason="supervised cold-start" if self._model is None
            else "supervised score",
            seed=self.seed,
        )

    def observe_reward(self, decision: PolicyDecision, reward: RewardEvent) -> None:
        """Accumulate a training row; refit lazily on the next :meth:`fit`."""
        self._rows.append({
            "context_key": decision.context_key,
            "action_key": decision.action.key(),
            "reward": reward.reward,
        })
