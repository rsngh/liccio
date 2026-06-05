"""Evidence-gap analyzer + experiment planner (Alpha 32 seed)."""

from __future__ import annotations

import pytest

from acp.observability.evidence_gap import (
    EvidenceGap,
    analyze_evidence_gaps,
    plan_experiments,
)


def _health(**over):
    h = {
        "production_gates": {"docker_live_security_passed": True,
                             "report_truth_consistent": True,
                             "benchmark_baseline_present": True},
        "benchmark": {"baseline_overall": 0.66, "discriminating": True,
                      "skill_ab_decision": "promote"},
        "measurement": {},
    }
    h.update(over)
    return h


def test_clean_health_has_no_high_gaps() -> None:
    gaps = analyze_evidence_gaps(_health())
    assert all(g.severity != "high" for g in gaps)


def test_failed_gate_becomes_a_gap_with_experiment() -> None:
    h = _health(production_gates={"docker_live_security_passed": False,
                                  "report_truth_consistent": True})
    gaps = analyze_evidence_gaps(h)
    docker = next(g for g in gaps if g.dimension == "docker_live_security_passed")
    assert docker.severity == "high"
    assert "docker-security-live" in docker.recommended_experiment


def test_ceiling_benchmark_flags_discrimination_gap() -> None:
    h = _health(benchmark={"baseline_overall": 1.0, "discriminating": False,
                           "skill_ab_decision": "abstain"})
    gaps = analyze_evidence_gaps(h)
    assert any(g.dimension == "benchmark_discrimination" for g in gaps)
    assert any("hard" in g.recommended_experiment for g in gaps)


def test_low_vendor_activation_flags_untrustworthy() -> None:
    h = _health(measurement={"vendor_activation_rate": 0.3})
    gaps = analyze_evidence_gaps(h)
    assert any(g.dimension == "vendor_activation" for g in gaps)


def test_gaps_sorted_most_severe_first() -> None:
    h = _health(production_gates={"docker_live_security_passed": False},  # high
                measurement={"vendor_activation_rate": 0.3})              # medium
    gaps = analyze_evidence_gaps(h)
    assert gaps[0].severity == "high"


def test_experiment_plan_dedups_and_respects_budget() -> None:
    h = _health(production_gates={"docker_live_security_passed": False,
                                  "report_truth_consistent": False,
                                  "benchmark_baseline_present": False})
    plan = plan_experiments(h, budget=2)
    assert len(plan.plan) == 2 and plan.n_gaps >= 3
    assert plan.by_severity.get("high", 0) >= 1


def test_bad_severity_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceGap("x", "catastrophic", "d", "e")
