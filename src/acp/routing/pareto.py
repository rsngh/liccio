"""Multi-objective Pareto routing (Alpha 9).

Routing on a single scalar reward hides trade-offs: a cheap agent that solves 70%
of tasks and a frontier agent that solves 95% at 5x the cost are both rational
choices depending on what you value. This module computes the Pareto-optimal
(non-dominated) set of candidate actions over the objectives
``(success↑, cost↓, latency↓, risk↓)`` and lets a weight profile pick one point on
the frontier — while exposing the whole frontier for inspection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ObjectiveVector:
    """A candidate's objectives. success is maximized; cost/latency/risk minimized."""

    success: float          # higher is better (0..1)
    cost: float             # lower is better (USD)
    latency: float          # lower is better (seconds)
    risk: float             # lower is better (0..1; e.g. post-merge-failure rate)

    def oriented(self) -> tuple[float, float, float, float]:
        """All objectives oriented so higher is better (negate the minimized ones)."""
        return (self.success, -self.cost, -self.latency, -self.risk)


def dominates(a: ObjectiveVector, b: ObjectiveVector) -> bool:
    """True if ``a`` Pareto-dominates ``b`` (>= on all objectives, > on at least one)."""
    av, bv = a.oriented(), b.oriented()
    return all(x >= y for x, y in zip(av, bv, strict=True)) and any(
        x > y for x, y in zip(av, bv, strict=True))


def pareto_frontier(items: list[T], key: Callable[[T], ObjectiveVector]) -> list[T]:
    """The non-dominated subset of ``items`` (order preserved)."""
    vecs = [key(it) for it in items]
    frontier: list[T] = []
    for i, it in enumerate(items):
        if not any(j != i and dominates(vecs[j], vecs[i]) for j in range(len(items))):
            frontier.append(it)
    return frontier


def scalarize(
    vec: ObjectiveVector, weights: dict[str, float], *, bounds: dict[str, tuple[float, float]]
) -> float:
    """Weighted sum of normalized, higher-is-better objectives in [0,1] per axis."""
    def nrm(name: str, value: float, *, maximize: bool) -> float:
        lo, hi = bounds[name]
        span = hi - lo
        x = 1.0 if span <= 0 else (value - lo) / span
        return x if maximize else 1.0 - x
    total = (
        weights.get("success", 0.0) * nrm("success", vec.success, maximize=True)
        + weights.get("cost", 0.0) * nrm("cost", vec.cost, maximize=False)
        + weights.get("latency", 0.0) * nrm("latency", vec.latency, maximize=False)
        + weights.get("risk", 0.0) * nrm("risk", vec.risk, maximize=False)
    )
    wsum = sum(weights.get(k, 0.0) for k in ("success", "cost", "latency", "risk"))
    return total / wsum if wsum else 0.0


@dataclass
class ParetoRouter(Generic[T]):
    """Selects a routing action from the Pareto frontier under a weight profile."""

    key: Callable[[T], ObjectiveVector]
    weights: dict[str, float]

    def _bounds(self, items: list[T]) -> dict[str, tuple[float, float]]:
        vs = [self.key(it) for it in items]
        return {
            "success": (min(v.success for v in vs), max(v.success for v in vs)),
            "cost": (min(v.cost for v in vs), max(v.cost for v in vs)),
            "latency": (min(v.latency for v in vs), max(v.latency for v in vs)),
            "risk": (min(v.risk for v in vs), max(v.risk for v in vs)),
        }

    def choose(self, items: list[T]) -> tuple[T | None, dict]:
        if not items:
            return None, {"frontier_size": 0, "chosen": None, "reason": "no candidates"}
        frontier = pareto_frontier(items, self.key)
        bounds = self._bounds(items)
        chosen = max(frontier, key=lambda it: scalarize(self.key(it), self.weights,
                                                         bounds=bounds))
        return chosen, {
            "frontier_size": len(frontier),
            "dominated_count": len(items) - len(frontier),
            "weights": self.weights,
            "chosen_score": round(scalarize(self.key(chosen), self.weights, bounds=bounds), 4),
        }


def cell_objective(cell) -> ObjectiveVector:  # noqa: ANN001 - duck-typed CapabilityCell
    """Build an ObjectiveVector from a CapabilityCell (risk = post-merge failure)."""
    risk = getattr(cell, "post_merge_failure_rate", None)
    if risk is None:
        risk = getattr(cell, "human_review_rate", 0.0)
    return ObjectiveVector(
        success=float(getattr(cell, "success_rate", 0.0)),
        cost=float(getattr(cell, "cost", 0.0)),
        latency=float(getattr(cell, "latency", 0.0)),
        risk=float(risk or 0.0),
    )
