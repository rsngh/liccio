"""Measurement mutation suite v3 (Alpha 14 WS13).

The strongest statement of the contract: a contaminated measurement must not update
solve-rate AND must not promote a policy. Each mutation is detected by some layer of
the measurement-trust stack (classifier, hygiene, quality score, availability audit).
"""

from __future__ import annotations

from acp.evaluation.harness_availability import audit_harness_availability
from acp.evaluation.learning_gate import gate_quality_samples
from acp.evaluation.measurement_hygiene import build_hygiene_report
from acp.evaluation.measurement_quality import measurement_quality_report
from acp.routing.capability_matrix import CapabilityMatrix
from acp.routing.ope import OPESample, fit_reward_model


def _ok(**kw):
    base = {"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
            "success": True, "status": "succeeded", "tool_calls": 2, "commands": 1,
            "file_reads": 1, "cost_usd": 0.001}
    base.update(kw)
    return base


def _timeout_before(**kw):
    return _ok(success=False, status="timed_out", timed_out=True, tool_calls=0,
               commands=0, file_reads=0, error="Request timed out.", cost_usd=0.0, **kw)


def test_v3_missing_harness_detected() -> None:
    rep = audit_harness_availability({"openai_harness"},
                                     env={"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"})
    assert rep.degraded


def test_v3_provider_500_and_429_classified_infra() -> None:
    h = build_hygiene_report([_ok(success=False, status="failed", error="500 server error"),
                              _ok(success=False, status="failed", error="429 rate limit")])
    assert h.n_infra == 2 and h.n_conclusive == 0


def test_v3_reward_model_cannot_be_poisoned() -> None:
    # A contaminated batch yields the SAME fitted reward as the clean batch.
    clean = [_ok() for _ in range(5)]
    poisoned = clean + [_timeout_before() for _ in range(8)]

    def q(cells):
        gated = gate_quality_samples(cells)
        s = [OPESample("bugfix", c["adapter"], 1.0, 1.0 if c["success"] else 0.0,
                       ["openai_harness"]) for c in gated]
        return fit_reward_model(s)("bugfix", "openai_harness")
    assert q(clean) == q(poisoned) == 1.0


def test_v3_policy_promotion_blocked_when_contaminated() -> None:
    # A contaminated run fails the measurement-quality trust gate -> not promotable.
    contaminated = [_ok()] + [_timeout_before() for _ in range(6)]
    rep = measurement_quality_report(contaminated)
    assert not rep.trusted  # the gate the promotion path consults


def test_v3_solve_rate_unchanged_under_all_infra_mutations() -> None:
    clean = [_ok() for _ in range(5)]
    mutated = clean + [
        _timeout_before(),
        _ok(success=False, status="failed", error="429 rate limit"),
        _ok(success=False, status="failed", error="503 service unavailable"),
        # solved-despite-hang -> a conclusive success, not infra noise:
        _ok(success=True, status="timed_out", timed_out=True, error="timed out"),
    ]
    base = CapabilityMatrix.from_bakeoff_report({"cells": clean}).cells()[0]
    mut = CapabilityMatrix.from_bakeoff_report({"cells": mutated}).cells()[0]
    # The solved-despite-hang counts as a success (conclusive); the rest are excluded.
    assert base.success_rate == 1.0 and mut.success_rate == 1.0
