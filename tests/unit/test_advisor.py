"""Layered advisor / metacognitive escalation (Alpha 24 area 1)."""

from __future__ import annotations

import pytest

from acp.orchestration.advisor import (
    AdvisorBudget,
    AdvisorCall,
    AdvisorPolicy,
    AdvisorResponse,
    ExecutorState,
    classify_trigger,
    consult_advisor,
)


def _advisor(_call: AdvisorCall) -> AdvisorResponse:
    return AdvisorResponse(recommendation="revise_plan", next_steps=["reproduce the bug"],
                           risk="medium", confidence=0.8)


def test_easy_low_risk_task_is_not_escalated() -> None:
    st = ExecutorState(task_name="divide", difficulty="easy", risk="low", confidence=1.0)
    assert classify_trigger(st) is None
    b = AdvisorBudget(max_calls=1)
    assert consult_advisor(st, advisor_fn=_advisor, budget=b) is None
    assert b.used == 0  # advisor not wasted on easy work


def test_high_risk_always_escalates() -> None:
    st = ExecutorState(task_name="auth", difficulty="easy", risk="high")
    assert classify_trigger(st) == "high_risk"


def test_repeated_failure_triggers_and_charges_budget() -> None:
    st = ExecutorState(task_name="roman", difficulty="hard", risk="medium",
                       consecutive_failures=2, evidence_summary="2 pytest failures")
    b = AdvisorBudget(max_calls=1)
    call = consult_advisor(st, advisor_fn=_advisor, budget=b)
    assert call is not None and call.trigger == "repeated_test_failure"
    assert call.advisor_response.recommendation == "revise_plan"
    assert b.used == 1 and not b.can_call()  # budget exhausted


def test_budget_caps_calls() -> None:
    st = ExecutorState(task_name="x", difficulty="hard", risk="high")
    b = AdvisorBudget(max_calls=1)
    assert consult_advisor(st, advisor_fn=_advisor, budget=b) is not None
    assert consult_advisor(st, advisor_fn=_advisor, budget=b) is None  # over budget


def test_trigger_precedence_and_thresholds() -> None:
    p = AdvisorPolicy(low_confidence_threshold=0.5)
    assert classify_trigger(
        ExecutorState("a", "medium", confidence=0.3), p) == "low_confidence"
    assert classify_trigger(
        ExecutorState("a", "medium", ambiguous_spec=True), p) == "ambiguous_spec"
    assert classify_trigger(
        ExecutorState("a", "medium", verifier_disagreement=True), p) == "verifier_disagreement"


def test_bad_recommendation_rejected() -> None:
    with pytest.raises(ValueError):
        AdvisorResponse(recommendation="hack_the_tests")
