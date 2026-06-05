"""Bayesian beta-binomial canary statistics (Alpha 22 WS14)."""

from __future__ import annotations

from acp.training.skill_canary import bayesian_canary


def _cell(success):
    return {"task_type": "bugfix", "adapter": "codex_cli", "is_harness": True,
            "success": success, "status": "succeeded" if success else "failed",
            "tool_calls": 2, "commands": 1, "file_reads": 1}


def test_clear_improvement_high_probability_promotes() -> None:
    control = [_cell(i < 6) for i in range(20)]   # 30%
    canary = [_cell(True) for _ in range(20)]      # 100%
    res = bayesian_canary(control, canary)
    assert res.prob_canary_better > 0.95 and res.promote
    assert res.canary_rate > res.control_rate


def test_low_n_abstains() -> None:
    res = bayesian_canary([_cell(False) for _ in range(3)],
                          [_cell(True) for _ in range(3)], min_per_arm=5)
    assert not res.promote and any("low N" in r for r in res.reasons)


def test_no_improvement_does_not_promote() -> None:
    same = [_cell(i < 16) for i in range(20)]
    res = bayesian_canary(same, [_cell(i < 16) for i in range(20)])
    assert not res.promote and res.prob_canary_better < 0.95


def test_credible_intervals_reported() -> None:
    res = bayesian_canary([_cell(True) for _ in range(10)],
                          [_cell(True) for _ in range(10)])
    assert 0.0 <= res.control_ci[0] <= res.control_ci[1] <= 1.0
    assert 0.0 <= res.canary_ci[0] <= res.canary_ci[1] <= 1.0
