"""Tests for active-learning exploration executor (Alpha 11, WS9)."""

from __future__ import annotations

from acp.evaluation.capability_campaign import generate_campaign_report
from acp.learning.exploration_run import (
    ExplorationBudget,
    ExplorationResult,
    ExplorationRun,
    UncertaintySignals,
)


def _low_sample_matrix():
    """A deterministic matrix with under-sampled cells (repetitions below floor)."""
    return generate_campaign_report(
        task_types=("bugfix", "feature"),
        risk_levels=("low", "high"),
        repo_types=("python_lib",),
        adapters=("aider",),
        strategies=("repo_map",),
        repetitions=2,  # below MIN_SAMPLE=5 -> under-sampled cells
    )


def test_run_respects_sample_budget() -> None:
    matrix = _low_sample_matrix()
    budget = ExplorationBudget(max_samples=4, allowed_risk_levels=("low", "high"))
    result = ExplorationRun().run(matrix, budget=budget)
    assert isinstance(result, ExplorationResult)
    total = sum(s.n_samples for s in result.specs_run)
    assert total <= 4


def test_run_blocks_disallowed_risk() -> None:
    matrix = _low_sample_matrix()
    # Only low-risk probes allowed: every high-risk cell must be blocked.
    budget = ExplorationBudget(allowed_risk_levels=("low",))
    result = ExplorationRun().run(matrix, budget=budget)
    assert result.blocked_by_risk, "expected high-risk probes to be blocked"
    assert all("|high|" in key for key in result.blocked_by_risk)
    assert all(s.risk_level == "low" for s in result.specs_run)


def test_run_improves_coverage_and_overlap() -> None:
    matrix = _low_sample_matrix()
    budget = ExplorationBudget(allowed_risk_levels=("low", "high"))
    result = ExplorationRun().run(matrix, budget=budget, ope_overlap=0.4)
    assert result.coverage_after >= result.coverage_before
    assert result.coverage_delta == result.coverage_after - result.coverage_before
    assert result.coverage_delta > 0, "low-sample matrix should gain coverage"
    assert result.ope_overlap_after >= result.ope_overlap_before
    assert result.cost_spent >= 0.0


def test_run_with_explicit_signals_serializes() -> None:
    matrix = _low_sample_matrix()
    budget = ExplorationBudget(allowed_risk_levels=("low", "high"))
    signals = UncertaintySignals(
        capability_gaps=3,
        ope_overlap_gap=0.6,
        high_counterfactual_regret=0.2,
        drift_uncertainty=0.1,
    )
    assert signals.is_active()
    result = ExplorationRun().run(
        matrix, budget=budget, regret=0.2, signals=signals
    )
    d = result.to_dict()
    assert d["n_specs_run"] == len(result.specs_run)
    assert d["coverage_after"] >= d["coverage_before"]
