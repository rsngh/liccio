"""Staged skill canary platform (Alpha 21 WS11)."""

from __future__ import annotations

from acp.training.skill_canary_platform import (
    CanaryGuardrails,
    StageMetrics,
    evaluate_stage,
    run_staged_canary,
)


def _good():
    return StageMetrics(control_solve=0.6, canary_solve=0.9, control_cost=0.01,
                        canary_cost=0.011, measurement_quality=1.0, control_har=1.0,
                        canary_har=1.0, control_hfr=0.9, canary_hfr=0.95)


def test_clean_rollout_promotes_at_100() -> None:
    metrics = {s: _good() for s in (0.05, 0.25, 0.50, 1.0)}
    res = run_staged_canary(metrics)
    assert res.promoted and res.final_stage == 1.0
    assert all(v.decision == "advance" for v in res.stages)


def test_regression_at_a_stage_rolls_back() -> None:
    metrics = {0.05: _good(), 0.25: _good()}
    bad = _good()
    bad.canary_solve = 0.4  # regresses below control 0.6 at 50%
    metrics[0.50] = bad
    metrics[1.0] = _good()
    res = run_staged_canary(metrics)
    assert not res.promoted and res.final_stage == 0.50
    assert "solve-rate regression" in res.rollback_reason


def test_cost_spike_breaches() -> None:
    m = _good()
    m.canary_cost = 0.02  # > control 0.01 * 1.5
    v = evaluate_stage(0.25, m)
    assert v.decision == "rollback" and any("cost spike" in b for b in v.breaches)


def test_security_finding_blocks() -> None:
    m = _good()
    m.security_findings = 1
    v = evaluate_stage(0.05, m, CanaryGuardrails(allow_security_findings=False))
    assert v.decision == "rollback"


def test_har_drop_breaches() -> None:
    m = _good()
    m.canary_har = 0.5  # 0.5 drop from control 1.0
    v = evaluate_stage(0.5, m)
    assert v.decision == "rollback" and any("HAR" in b for b in v.breaches)
