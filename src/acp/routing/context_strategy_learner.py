"""Learned context-strategy selection (Alpha 8, WS3).

Trains a reward predictor over ``(task features, context_strategy)`` from the
context-strategy dataset (distilled from logged routing decisions + rewards, and
from the downstream benchmark), then lets the router pick the strategy with the
highest predicted reward for a task. Promotion to live routing still requires an
OPE + downstream-benchmark pass (the predictor only proposes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.routing.supervised import TrainResult, predict, train_predictor

# Strategy vocabulary the predictor scores over.
STRATEGIES = [
    "hybrid_keyword_embedding", "minimal", "test_focused",
    "bug_reproduction", "architecture", "recent_changes",
]


def _features(task_type: str, risk_level: str, strategy: str) -> dict[str, float]:
    """Bag-of-tokens over task type / risk / strategy — generalizes across arms."""
    feats: dict[str, float] = {}
    for tok in (f"tt={task_type}", f"risk={risk_level}", f"strat={strategy}"):
        feats[tok] = 1.0
    return feats


@dataclass
class ContextStrategyPredictor:
    name: str = "context_strategy_predictor"
    _model: TrainResult | None = None
    _keys: list[str] = field(default_factory=list)

    def fit(self, rows: list[dict[str, Any]]) -> None:
        """Rows of ``{"task_type", "risk_level", "context_strategy", "reward"}``."""
        feats_rows: list[dict[str, Any]] = []
        keys: set[str] = set()
        for r in rows:
            if r.get("reward") is None:
                continue
            f = _features(str(r.get("task_type")), str(r.get("risk_level")),
                          str(r.get("context_strategy")))
            f["reward"] = float(r["reward"])
            keys.update(k for k in f if k != "reward")
            feats_rows.append(f)
        self._keys = sorted(keys)
        if feats_rows:
            self._model = train_predictor(feats_rows, "reward", self._keys)

    def predicted_reward(self, task_type: str, risk_level: str, strategy: str) -> float:
        if self._model is None:
            return 0.0
        return predict(self._model, _features(task_type, risk_level, strategy))

    def rank(self, task_type: str, risk_level: str,
             strategies: list[str] | None = None) -> list[tuple[str, float]]:
        cands = strategies or STRATEGIES
        scored = [(s, self.predicted_reward(task_type, risk_level, s)) for s in cands]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored


@dataclass
class ContextStrategyPolicy:
    """Chooses a context strategy from the learned predictor (cold-start: default)."""

    predictor: ContextStrategyPredictor = field(default_factory=ContextStrategyPredictor)
    default_strategy: str = "hybrid_keyword_embedding"

    def choose(self, task_type: str, risk_level: str,
               allowed: list[str] | None = None) -> str:
        if self.predictor._model is None:
            return self.default_strategy
        ranked = self.predictor.rank(task_type, risk_level, allowed)
        return ranked[0][0] if ranked else self.default_strategy


def evaluate_context_strategy_predictor(
    predictor: ContextStrategyPredictor, cases: list[dict[str, Any]]
) -> dict:
    """Top-1 accuracy: does the predictor's best strategy match the gold-best per
    (task_type, risk_level) group implied by the cases' rewards?"""
    groups: dict[tuple[str, str], dict[str, list[float]]] = {}
    for c in cases:
        if c.get("reward") is None:
            continue
        key = (str(c.get("task_type")), str(c.get("risk_level")))
        groups.setdefault(key, {}).setdefault(str(c.get("context_strategy")), []).append(
            float(c["reward"]))
    correct = 0
    total = 0
    for (tt, risk), by_strat in groups.items():
        gold = max(by_strat, key=lambda s: sum(by_strat[s]) / len(by_strat[s]))
        pred = predictor.rank(tt, risk, list(by_strat))[0][0]
        total += 1
        if pred == gold:
            correct += 1
    return {"groups": total, "top1_accuracy": round(correct / total, 4) if total else 0.0}
