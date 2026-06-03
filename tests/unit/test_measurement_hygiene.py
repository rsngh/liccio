"""Attempt-outcome classification + hygiene report (Alpha 11/12 WS1)."""

from __future__ import annotations

from acp.core.enums import AttemptOutcome
from acp.evaluation.measurement_hygiene import (
    build_hygiene_report,
    classify_attempt,
)


def _cell(**kw):
    base = {"adapter": "openai_harness", "task_type": "bugfix", "success": False,
            "status": "failed", "error": None, "tool_calls": 1, "is_harness": True}
    base.update(kw)
    return base


def test_classify_task_success() -> None:
    assert classify_attempt(_cell(success=True, status="succeeded")) \
        == AttemptOutcome.TASK_SUCCESS


def test_classify_solved_despite_late_hang_is_success() -> None:
    o = classify_attempt(_cell(success=True, timed_out=True, error="Request timed out."))
    assert o == AttemptOutcome.INFRA_TIMEOUT_AFTER_SOLUTION
    assert o.is_success and o.is_conclusive_quality and o.is_infra


def test_classify_first_call_hang_is_inconclusive() -> None:
    o = classify_attempt(_cell(timed_out=True, error="Request timed out.", tool_calls=0))
    assert o == AttemptOutcome.INFRA_TIMEOUT_BEFORE_ACTION
    assert not o.is_conclusive_quality and o.is_infra


def test_classify_timeout_with_activity_is_task_failure() -> None:
    o = classify_attempt(_cell(timed_out=True, error="timed out", tool_calls=5))
    assert o == AttemptOutcome.TASK_FAILURE and o.is_conclusive_quality


def test_classify_provider_errors() -> None:
    assert classify_attempt(_cell(error="Error code: 429 rate limit")) \
        == AttemptOutcome.PROVIDER_RATE_LIMIT
    assert classify_attempt(_cell(error="500 internal server error")) \
        == AttemptOutcome.PROVIDER_SERVER_ERROR
    assert classify_attempt(_cell(error="max retries exceeded")) \
        == AttemptOutcome.PROVIDER_RETRY_EXCEEDED


def test_classify_harness_activation_failure() -> None:
    o = classify_attempt(_cell(tool_calls=0, is_harness=True, error="no edit"))
    assert o == AttemptOutcome.HARNESS_ACTIVATION_FAILURE and o.is_conclusive_quality


def test_classify_plain_task_failure() -> None:
    assert classify_attempt(_cell(tool_calls=3, is_harness=True)) \
        == AttemptOutcome.TASK_FAILURE


def test_hygiene_report_solve_rate_uses_conclusive_only() -> None:
    cells = [
        _cell(success=True, status="succeeded"),                        # success
        _cell(success=True, status="succeeded"),                        # success
        _cell(tool_calls=3),                                            # task_failure
        _cell(timed_out=True, error="timed out", tool_calls=0),        # infra (excl)
        _cell(error="429 rate limit"),                                 # provider (excl)
    ]
    rep = build_hygiene_report(cells)
    assert rep.n_attempts == 5
    assert rep.n_conclusive == 3            # 2 success + 1 task_failure
    assert rep.solve_rate == round(2 / 3, 4)
    assert rep.n_infra == 2                 # timeout-before-action + rate-limit
    assert rep.contaminated  # 2/5 = 40% inconclusive/infra > 30%


def test_hygiene_report_clean_is_not_contaminated() -> None:
    cells = [_cell(success=True, status="succeeded") for _ in range(9)] + [_cell(tool_calls=2)]
    rep = build_hygiene_report(cells)
    assert not rep.contaminated and rep.solve_rate == 0.9
