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


def test_harness_benefit_metrics_populate_from_signals() -> None:
    # WS6: cells carrying harness signals -> HAR/HFR/PWL on the capability cell.
    from acp.routing.capability_matrix import CapabilityMatrix
    cells = [{"task_type": "bugfix", "risk": "medium", "adapter": "openai_harness",
              "is_harness": True, "context_strategy": "hybrid_keyword_embedding",
              "success": i < 5, "cost_usd": 0.001, "latency_s": 3.0,
              "tool_calls": 2 if i < 5 else 0,  # one attempt didn't activate
              "file_reads": 1, "commands": 1} for i in range(6)]
    m = CapabilityMatrix.from_bakeoff_report({"cells": cells})
    cell = m.cells()[0]
    assert cell.har == round(5 / 6, 4)          # 5/6 activated
    assert cell.pwl == 1.0                       # all activated attempts solved
    assert "har" in cell.to_dict()


def test_non_harness_cells_have_no_benefit_metrics() -> None:
    from acp.routing.capability_matrix import CapabilityMatrix
    cells = [{"task_type": "bugfix", "risk": "medium", "adapter": "fake",
              "is_harness": False, "context_strategy": "minimal",
              "success": False, "cost_usd": 0.0, "latency_s": 0.0} for _ in range(3)]
    cell = CapabilityMatrix.from_bakeoff_report({"cells": cells}).cells()[0]
    assert cell.har is None and cell.hfr is None and cell.pwl is None


def _cell(adapter, succ, cost, lat, n=5):
    from acp.routing.capability_matrix import CapabilityCell
    c = CapabilityCell(task_type="bugfix", risk_level="medium", repo_type="python_package",
                       agent_class=adapter, context_strategy="hybrid", verification_policy="strict",
                       success_rate=succ, cost=cost, latency=lat, sample_size=n,
                       sufficient_data=True)
    return c


def test_score_cost_tiebreak_prefers_cheaper_on_equal_success() -> None:
    # Equal success -> cheaper+faster cell scores higher (cost-optimal route).
    from acp.routing.capability_matrix import CapabilityMatrix
    m = CapabilityMatrix()
    cheap = _cell("openai_harness", 1.0, 0.001, 5.0)
    pricey = _cell("claude_harness", 1.0, 0.0135, 7.0)
    assert m._score(cheap) > m._score(pricey)


def test_score_tiebreak_never_overrides_real_success_gap() -> None:
    # A genuine success gap (>= one sample) must dominate the cost tiebreak, even
    # when the better adapter is far more expensive.
    from acp.routing.capability_matrix import CapabilityMatrix
    m = CapabilityMatrix()
    capable_pricey = _cell("claude_harness", 1.0, 0.05, 18.0)
    cheap_worse = _cell("openai_harness", 0.2, 0.006, 23.0)
    assert m._score(capable_pricey) > m._score(cheap_worse)
