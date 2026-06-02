"""Unit tests for the active-learning exploration executor (Alpha 9, WS9)."""

from __future__ import annotations

from acp.evaluation.capability_campaign import generate_campaign_report
from acp.learning.exploration_executor import (
    ExplorationBudgetPolicy,
    ExplorationExecutor,
    ExplorationTaskGenerator,
)
from acp.routing.capability_matrix import CapabilityMatrix
from acp.routing.exploration import CoverageGapAnalyzer


def _matrix_with_low_sample_cells() -> CapabilityMatrix:
    """A campaign matrix guaranteed to carry under-sampled cells."""
    matrix = generate_campaign_report(repetitions=6)
    assert any(not c.sufficient_data for c in matrix.cells())
    return matrix


def test_generate_honors_risk_allowlist() -> None:
    matrix = _matrix_with_low_sample_cells()
    plan = CoverageGapAnalyzer().analyze(matrix)
    assert plan.targets

    policy = ExplorationBudgetPolicy(allowed_risk_levels=("low",))
    specs = ExplorationTaskGenerator().generate(plan, policy)

    assert specs, "expected at least one low-risk target to survive the allowlist"
    assert all(s.risk_level == "low" for s in specs)
    # higher-risk targets that exist in the plan must have been dropped
    dropped = [t for t in plan.targets if t.risk_level != "low"]
    assert dropped


def test_generate_honors_sample_and_cost_caps() -> None:
    matrix = _matrix_with_low_sample_cells()
    plan = CoverageGapAnalyzer().analyze(matrix)

    policy = ExplorationBudgetPolicy(max_samples=7, max_cost=0.05)
    specs = ExplorationTaskGenerator().generate(plan, policy)

    assert sum(s.n_samples for s in specs) <= 7
    assert sum(s.est_cost for s in specs) <= 0.05 + 1e-9


def test_simulate_increases_sufficient_coverage() -> None:
    matrix = _matrix_with_low_sample_cells()
    plan = CoverageGapAnalyzer().analyze(matrix)
    # allow every risk level so every gap can be filled in the simulation
    policy = ExplorationBudgetPolicy(
        allowed_risk_levels=("low", "medium", "high", "critical")
    )
    specs = ExplorationTaskGenerator().generate(plan, policy)
    assert specs

    before = sum(1 for c in matrix.cells() if c.sufficient_data)
    result = ExplorationExecutor().simulate(matrix, specs)

    assert result["before"]["n_sufficient"] == before
    assert result["specs_run"] == len(specs)
    assert result["coverage_delta"] > 0
    assert result["after"]["n_sufficient"] > result["before"]["n_sufficient"]

    # original matrix must be untouched (work happened on a copy)
    assert sum(1 for c in matrix.cells() if c.sufficient_data) == before


def test_simulate_empty_specs_is_noop() -> None:
    matrix = _matrix_with_low_sample_cells()
    result = ExplorationExecutor().simulate(matrix, [])
    assert result["coverage_delta"] == 0
    assert result["specs_run"] == 0
