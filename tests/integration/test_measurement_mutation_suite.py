"""Measurement mutation suite (Alpha 11/12 WS11).

Deliberately inject each measurement flaw the live bakeoff exposed and assert the
measurement-trust layer DETECTS it — so a future regression that silently corrupts
routing evidence fails a test instead of shipping.
"""

from __future__ import annotations

from acp.core.enums import AttemptOutcome
from acp.evaluation.harness_availability import audit_harness_availability
from acp.evaluation.measurement_hygiene import build_hygiene_report, classify_attempt


def _cell(**kw):
    base = {"adapter": "openai_harness", "task_type": "bugfix", "success": False,
            "status": "failed", "error": None, "tool_calls": 2, "is_harness": True}
    base.update(kw)
    return base


def test_mutation_hide_claude_key_is_detected() -> None:
    # Both keys present but claude never built (the cached-settings bug).
    rep = audit_harness_availability(
        {"openai_harness"}, env={"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"})
    assert rep.degraded and "claude_harness" in rep.silently_absent


def test_mutation_provider_500_not_counted_as_model_failure() -> None:
    o = classify_attempt(_cell(error="Error code 500 internal server error"))
    assert o == AttemptOutcome.PROVIDER_SERVER_ERROR
    assert not o.is_conclusive_quality  # excluded from solve-rate


def test_mutation_provider_429_classified_infra() -> None:
    o = classify_attempt(_cell(error="429 Too Many Requests"))
    assert o == AttemptOutcome.PROVIDER_RATE_LIMIT and o.is_infra


def test_mutation_post_solve_timeout_kept_as_success() -> None:
    o = classify_attempt(_cell(success=True, timed_out=True, error="Request timed out."))
    assert o.is_success and o == AttemptOutcome.INFRA_TIMEOUT_AFTER_SOLUTION


def test_mutation_first_call_hang_excluded() -> None:
    o = classify_attempt(_cell(timed_out=True, error="timed out", tool_calls=0))
    assert not o.is_conclusive_quality


def test_mutation_disable_tool_choice_shows_activation_failure() -> None:
    # Without tool_choice="required" the model returns prose -> zero tool calls on a
    # harness -> activation failure (conclusive, attributable to the harness config).
    o = classify_attempt(_cell(tool_calls=0, error="no edit produced"))
    assert o == AttemptOutcome.HARNESS_ACTIVATION_FAILURE


def test_mutation_burst_of_infra_contaminates_report() -> None:
    # A run dominated by infra hangs must be flagged contaminated so its solve_rate
    # is not trusted (the "Claude dominates security" false conclusion).
    cells = ([_cell(success=True, status="succeeded")]
             + [_cell(timed_out=True, error="timed out", tool_calls=0) for _ in range(4)])
    rep = build_hygiene_report(cells)
    assert rep.contaminated and rep.n_infra == 4
    # Solve-rate is computed over the single conclusive attempt, not 1/5.
    assert rep.solve_rate == 1.0 and rep.n_conclusive == 1
