"""Unit tests for the policy canary simulator (Alpha 8, WS10)."""

from __future__ import annotations

from acp.routing.canary import (
    CanaryGuardrails,
    PolicyCanaryExecutor,
)
from acp.routing.promotion import PolicyCanaryPlan


def _guardrails() -> CanaryGuardrails:
    return CanaryGuardrails(
        dr_ci_lower_bound=0.6,
        max_human_review_rate=0.3,
        max_cost=1.0,
    )


def _plan() -> PolicyCanaryPlan:
    return PolicyCanaryPlan(stages=[0.05, 0.25, 0.5, 1.0])


def _ok(reward: float = 0.8) -> dict:
    return {
        "observed_reward": reward,
        "observed_human_review_rate": 0.1,
        "observed_cost": 0.5,
        "high_risk_failures": 0,
        "security_regressions": 0,
    }


def test_all_stages_pass_full_promotion_no_rollback() -> None:
    executor = PolicyCanaryExecutor(_plan(), _guardrails())
    results, decision = executor.run([_ok(), _ok(), _ok(), _ok()])

    assert len(results) == 4
    assert all(r.passed for r in results)
    assert decision.rolled_back is False
    assert decision.stopped_at_stage is None
    assert results[-1].stage_fraction == 1.0


def test_reward_below_floor_rolls_back_and_skips_later_stages() -> None:
    executor = PolicyCanaryExecutor(_plan(), _guardrails())
    metrics = [_ok(), _ok(reward=0.4), _ok(), _ok()]
    results, decision = executor.run(metrics)

    # First stage passes, second breaches; stages 3 and 4 are not executed.
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False
    assert decision.rolled_back is True
    assert decision.stopped_at_stage == 0.25
    assert "below DR CI lower bound" in (decision.reason or "")


def test_human_review_spike_rolls_back() -> None:
    executor = PolicyCanaryExecutor(_plan(), _guardrails())
    spike = _ok()
    spike["observed_human_review_rate"] = 0.9
    results, decision = executor.run([spike])

    assert decision.rolled_back is True
    assert decision.stopped_at_stage == 0.05
    assert "human-review rate" in (decision.reason or "")
    assert results[0].breach_reasons


def test_high_risk_failure_rolls_back() -> None:
    executor = PolicyCanaryExecutor(_plan(), _guardrails())
    bad = _ok()
    bad["high_risk_failures"] = 1
    results, decision = executor.run([_ok(), bad])

    assert decision.rolled_back is True
    assert decision.stopped_at_stage == 0.25
    assert "high-risk task failure" in (decision.reason or "")
    assert results[1].high_risk_failures == 1


def test_rollback_reason_recorded_on_stage_and_decision() -> None:
    executor = PolicyCanaryExecutor(_plan(), _guardrails())
    bad = _ok()
    bad["security_regressions"] = 2
    results, decision = executor.run([bad])

    assert decision.rolled_back is True
    assert decision.reason == "; ".join(results[0].breach_reasons)
    assert "security regression" in (decision.reason or "")
    assert decision.as_dict()["stopped_at_stage"] == 0.05
