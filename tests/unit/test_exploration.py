"""Unit tests for the exploration policy designer (Alpha 8, WS12)."""

from __future__ import annotations

import json

from acp.routing.capability_matrix import MIN_SAMPLE, CapabilityMatrix
from acp.routing.exploration import (
    CoverageGapAnalyzer,
    ExplorationBudget,
)


def _bakeoff_report() -> dict:
    """Synthetic bakeoff: 'refactor' well-sampled, 'migrate' under-sampled."""
    cells: list[dict] = []
    # 6 runs of refactor/claude -> above the MIN_SAMPLE=5 floor.
    for _ in range(6):
        cells.append({
            "task": "refactor", "risk": "low", "agent_class": "claude",
            "success": True, "cost_usd": 0.05, "latency_s": 1.0,
            "human_review_required": False,
        })
    # 2 runs of migrate/claude -> under-sampled.
    for _ in range(2):
        cells.append({
            "task": "migrate", "risk": "high", "agent_class": "claude",
            "success": True, "cost_usd": 0.08, "latency_s": 2.0,
            "human_review_required": True,
        })
    # 1 run of audit/simple_llm -> most ignorant cell.
    cells.append({
        "task": "audit", "risk": "low", "agent_class": "simple_llm",
        "success": False, "cost_usd": 0.02, "latency_s": 0.5,
        "human_review_required": False,
    })
    return {"cells": cells}


def _matrix() -> CapabilityMatrix:
    return CapabilityMatrix.from_bakeoff_report(_bakeoff_report())


def test_flags_only_under_sampled_cells() -> None:
    matrix = _matrix()
    plan = CoverageGapAnalyzer().analyze(matrix)

    tasks = {t.task_type for t in plan.targets}
    assert tasks == {"migrate", "audit"}  # refactor (n=6) excluded
    for t in plan.targets:
        assert t.samples_needed > 0
        assert t.current_sample_size < MIN_SAMPLE
        assert t.samples_needed == MIN_SAMPLE - t.current_sample_size


def test_recommended_policy_and_risk_note() -> None:
    matrix = _matrix()
    plan = CoverageGapAnalyzer().analyze(
        matrix,
        budget=ExplorationBudget(risk_constraints=["low_risk_only_for_live"]),
    )
    by_task = {t.task_type: t for t in plan.targets}

    # known agent class -> explore:<agent>; default agent class -> generic explore
    assert by_task["migrate"].recommended_policy == "explore:claude"
    assert by_task["audit"].recommended_policy == "explore"
    # high-risk migrate cell must carry a sandbox note
    assert "sandbox" in by_task["migrate"].risk_note or "Docker" in by_task["migrate"].risk_note
    assert by_task["migrate"].risk_level == "high"


def test_budget_caps_total_samples() -> None:
    matrix = _matrix()
    # audit needs 4, migrate needs 3 -> 7 total; cap at 5.
    plan = CoverageGapAnalyzer().analyze(
        matrix, budget=ExplorationBudget(max_samples=5)
    )
    assert plan.total_samples == 5
    assert sum(t.samples_needed for t in plan.targets) == 5


def test_summary_mentions_concrete_cell() -> None:
    plan = CoverageGapAnalyzer().analyze(_matrix())
    # most-ignorant cell (audit, n=1) leads the summary
    assert "audit" in plan.summary
    assert "more" in plan.summary and "samples" in plan.summary


def test_to_dict_json_serializable() -> None:
    plan = CoverageGapAnalyzer().analyze(
        _matrix(), budget=ExplorationBudget(max_samples=10, max_cost_usd=1.0)
    )
    d = plan.to_dict()
    encoded = json.dumps(d)  # must not raise
    assert json.loads(encoded)["n_targets"] == len(plan.targets)
    assert d["total_samples"] == plan.total_samples
    assert d["budget"]["max_samples"] == 10
