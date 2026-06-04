"""AttemptOutcome hard invariant (Alpha 14 WS2).

The single proof that a contaminated live attempt cannot update solve-rate or OPE
quality reward — across the capability matrix AND the OPE builder, end to end.
"""

from __future__ import annotations

import pytest

from acp.evaluation.learning_gate import (
    ContaminatedSampleError,
    assert_quality_eligible,
    gate_quality_samples,
)
from acp.routing.capability_matrix import CapabilityMatrix
from acp.routing.ope import OPESample, fit_reward_model


def _ok(**kw):
    base = {"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
            "success": True, "status": "succeeded", "tool_calls": 2, "commands": 1,
            "file_reads": 1, "cost_usd": 0.001}
    base.update(kw)
    return base


def _contaminated():
    # An infra timeout before any tool call — must never touch quality metrics.
    return _ok(success=False, status="timed_out", timed_out=True, tool_calls=0,
               commands=0, file_reads=0, error="Request timed out.", cost_usd=0.0)


def test_assert_quality_eligible_rejects_contaminated() -> None:
    assert_quality_eligible(_ok())  # conclusive -> ok
    with pytest.raises(ContaminatedSampleError):
        assert_quality_eligible(_contaminated())


def test_contaminated_attempt_cannot_change_matrix_solve_rate() -> None:
    clean = [_ok() for _ in range(5)]
    base = CapabilityMatrix.from_bakeoff_report({"cells": clean}).cells()[0]
    # Inject 5 contaminated infra timeouts.
    poisoned = CapabilityMatrix.from_bakeoff_report(
        {"cells": clean + [_contaminated() for _ in range(5)]}).cells()[0]
    assert base.success_rate == poisoned.success_rate == 1.0
    assert base.conclusive_sample_size == poisoned.conclusive_sample_size == 5


def test_contaminated_attempt_cannot_change_ope_quality_reward() -> None:
    # Build OPE quality reward from gated (conclusive-only) samples; the contaminated
    # rows are filtered, so the fitted reward model is identical.
    clean = [_ok() for _ in range(5)]
    noisy = clean + [_contaminated() for _ in range(5)]

    def reward(cells):
        gated = gate_quality_samples(cells)
        samples = [OPESample("bugfix", c["adapter"], 1.0, 1.0 if c["success"] else 0.0,
                             ["openai_harness"]) for c in gated]
        q = fit_reward_model(samples)
        return q("bugfix", "openai_harness")

    assert reward(clean) == reward(noisy) == 1.0
