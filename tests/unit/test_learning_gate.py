"""AttemptOutcome as the mandatory learning gate (Alpha 13 WS2)."""

from __future__ import annotations

from acp.evaluation.learning_gate import (
    eligible_for_quality,
    gate_quality_samples,
    split_for_learning,
)
from acp.evaluation.measurement_hygiene import classify_record


def _cell(**kw):
    base = {"adapter": "openai_harness", "task_type": "bugfix", "success": False,
            "status": "failed", "error": None, "tool_calls": 2, "is_harness": True,
            "commands": 1, "file_reads": 1, "cost_usd": 0.001}
    base.update(kw)
    return base


def test_infra_attempt_not_eligible_for_quality() -> None:
    infra = _cell(timed_out=True, error="timed out", tool_calls=0)
    assert not eligible_for_quality(infra)
    assert eligible_for_quality(_cell(success=True, status="succeeded"))


def test_gate_drops_contaminated_from_quality() -> None:
    cells = [
        _cell(success=True, status="succeeded"),
        _cell(error="429 rate limit"),                          # provider -> excluded
        _cell(timed_out=True, error="timed out", tool_calls=0), # infra -> excluded
        _cell(tool_calls=3),                                    # task_failure -> kept
    ]
    quality, reliability_only = split_for_learning(cells)
    assert len(quality) == 2          # success + task_failure
    assert len(reliability_only) == 2
    assert len(gate_quality_samples(cells)) == 2


def test_record_learning_gate_fields() -> None:
    r = classify_record(_cell(success=True, status="succeeded"))
    assert r.conclusive and r.include_in_quality_denominator
    assert r.verification_valid and r.tool_activation_valid
    assert r.harness_adherence_valid and r.cost_billable
    infra = classify_record(_cell(timed_out=True, error="timed out", tool_calls=0,
                                  commands=0, file_reads=0, cost_usd=0.0))
    assert not infra.include_in_quality_denominator
    assert infra.contaminated and infra.infra_failure_kind == "timeout_before_action"
    assert not infra.tool_activation_valid and not infra.cost_billable
