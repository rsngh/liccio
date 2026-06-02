"""Tests for the capability matrix (alpha-7 WS2)."""

from __future__ import annotations

import json

from acp.routing.capability_matrix import MIN_SAMPLE, CapabilityMatrix
from acp.schemas.learning import PostMergeOutcome


def _report() -> dict:
    """A synthetic bakeoff v2-shaped report.

    bugfix/medium: adapter_a has 6 runs (4 successes), adapter_b has 6 runs
    (1 success). feature/low: adapter_a has only 2 runs (low sample).
    """
    cells: list[dict] = []
    for i in range(6):
        cells.append({
            "task": "t1", "task_type": "bugfix", "risk": "medium",
            "adapter": "adapter_a", "success": i < 4,
            "cost_usd": 0.10, "latency_s": 2.0,
            "human_review_required": i == 0,
        })
    for i in range(6):
        cells.append({
            "task": "t1", "task_type": "bugfix", "risk": "medium",
            "adapter": "adapter_b", "success": i < 1,
            "cost_usd": 0.50, "latency_s": 5.0,
            "human_review_required": False,
        })
    for _i in range(2):
        cells.append({
            "task": "t2", "task_type": "feature", "risk": "low",
            "adapter": "adapter_a", "success": True,
            "cost_usd": 0.20, "latency_s": 3.0,
            "human_review_required": False,
        })
    return {"cells": cells}


def test_builds_and_aggregates() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report(), repo_type="python_lib")
    cells = {(c.task_type, c.agent_class): c for c in m.cells()}
    a = cells[("bugfix", "adapter_a")]
    assert a.sample_size == 6
    assert a.success_rate == round(4 / 6, 4)
    assert a.cost == 0.10
    assert a.latency == 2.0
    assert a.human_review_rate == round(1 / 6, 4)
    assert a.repo_type == "python_lib"
    assert a.sufficient_data is True


def test_low_sample_flagged() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    feature = next(c for c in m.cells() if c.task_type == "feature")
    assert feature.sample_size == 2 < MIN_SAMPLE
    assert feature.sufficient_data is False
    assert "low_sample" in feature.flags


def test_best_for_skips_low_sample() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    # bugfix/medium: adapter_a (4/6) beats adapter_b (1/6)
    best, reason = m.best_for("bugfix", "medium", "unknown")
    assert best is not None
    assert best.agent_class == "adapter_a"
    assert "confident" in reason
    # feature/low has only a low-sample cell -> refuse to recommend
    none, reason2 = m.best_for("feature", "low", "unknown")
    assert none is None
    assert "low_sample" in reason2


def test_update_from_outcomes_raises_failure_and_flips_best() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    a = next(c for c in m.cells() if c.agent_class == "adapter_a"
             and c.task_type == "bugfix")
    b = next(c for c in m.cells() if c.agent_class == "adapter_b"
             and c.task_type == "bugfix")
    # adapter_a was best by success. Now it reverts in the field a lot.
    a_outcomes = [PostMergeOutcome(task_id="t1", reverted=True) for _ in range(5)]
    b_outcomes = [PostMergeOutcome(task_id="t1", reverted=False) for _ in range(5)]
    n = m.update_from_outcomes(
        a_outcomes, task_keys={"t1": a.key()})
    m.update_from_outcomes(b_outcomes, task_keys={"t1": b.key()})
    assert n == 5
    assert a.post_merge_failure_rate == 1.0
    assert a.post_merge_sample_size == 5
    assert b.post_merge_failure_rate == 0.0
    # adapter_a's success (0.67) minus failure (1.0) = -0.33; adapter_b 0.167-0 > that
    best, _ = m.best_for("bugfix", "medium", "unknown")
    assert best is not None
    assert best.agent_class == "adapter_b"


def test_attach_ope_sets_column() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    a = next(c for c in m.cells() if c.agent_class == "adapter_a"
             and c.task_type == "bugfix")
    updated = m.attach_ope({"per_cell": {a.key_str(): {"estimate": 0.42}}})
    assert updated == 1
    assert a.ope_estimated_reward == 0.42
    # scalar form also works
    updated2 = m.attach_ope({a.key_str(): 0.9})
    assert updated2 == 1
    assert a.ope_estimated_reward == 0.9


def test_to_dict_json_serializable() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    m.update_from_outcomes([PostMergeOutcome(task_id="t1", reverted=True)])
    d = m.to_dict()
    s = json.dumps(d)  # must not raise
    assert d["min_sample"] == MIN_SAMPLE
    assert d["n_cells"] == len(m.cells())
    assert isinstance(json.loads(s)["cells"][0]["last_updated"], str)


def test_explain_ranks_cells() -> None:
    m = CapabilityMatrix.from_bakeoff_report(_report())
    out = m.explain(("bugfix", "medium", "unknown"))
    assert out["n_cells"] == 2
    assert out["ranked"][0]["agent_class"] == "adapter_a"
    assert out["best"]["agent_class"] == "adapter_a"
