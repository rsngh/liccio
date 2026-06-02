"""Multi-objective Pareto routing (Alpha 9)."""

from __future__ import annotations

from acp.routing.pareto import (
    ObjectiveVector,
    ParetoRouter,
    dominates,
    pareto_frontier,
)


def _v(success, cost, latency=1.0, risk=0.0):
    return ObjectiveVector(success=success, cost=cost, latency=latency, risk=risk)


def test_dominates_clear_and_incomparable() -> None:
    strong = _v(0.9, 0.1)
    weak = _v(0.5, 0.5)
    assert dominates(strong, weak)
    assert not dominates(weak, strong)
    # Trade-off pair: cheaper-but-worse vs pricier-but-better -> incomparable.
    cheap = _v(0.6, 0.1)
    good = _v(0.95, 0.9)
    assert not dominates(cheap, good)
    assert not dominates(good, cheap)
    # Equal vectors do not dominate each other.
    assert not dominates(_v(0.7, 0.3), _v(0.7, 0.3))


def test_frontier_keeps_tradeoffs_drops_dominated() -> None:
    items = {
        "cheap_ok": _v(0.6, 0.1),
        "expensive_great": _v(0.95, 0.9),
        "dominated": _v(0.5, 0.5),  # worse success AND worse cost than cheap_ok
    }
    keys = list(items)
    frontier = pareto_frontier(keys, key=lambda k: items[k])
    assert "cheap_ok" in frontier and "expensive_great" in frontier
    assert "dominated" not in frontier


def test_scalarization_weight_profiles_pick_differently() -> None:
    items = {"cheap": _v(0.6, 0.1), "great": _v(0.95, 1.0)}

    def key(k):
        return items[k]

    success_pick, _ = ParetoRouter(key=key, weights={"success": 1.0}).choose(list(items))
    cost_pick, info = ParetoRouter(key=key, weights={"cost": 1.0}).choose(list(items))
    assert success_pick == "great"
    assert cost_pick == "cheap"
    assert info["frontier_size"] == 2 and "chosen_score" in info


def test_cell_objective_from_capability_cell() -> None:
    from acp.routing.capability_matrix import CapabilityMatrix
    from acp.routing.pareto import cell_objective

    cells = [{"task_type": "bugfix", "risk": "medium", "adapter": "claude_harness",
              "is_harness": True, "context_strategy": "test_focused",
              "success": True, "cost_usd": 0.02, "latency_s": 3.0} for _ in range(6)]
    matrix = CapabilityMatrix.from_bakeoff_report({"cells": cells})
    vec = cell_objective(matrix.cells()[0])
    assert vec.success > 0.0 and vec.cost >= 0.0
