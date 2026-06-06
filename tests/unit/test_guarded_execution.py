"""Guarded execution ladder (Alpha 30)."""

from __future__ import annotations

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.orchestration.guarded_execution import (
    DraftPatch,
    ExecutionMode,
    GuardrailPolicy,
    guard,
    produce_draft_patch,
)

DIVIDE = next(t for t in BENCH_TASKS if t.name == "divide")


def test_draft_modes_pass_through() -> None:
    d = guard(task_id="t", requested_mode=ExecutionMode.DRAFT_PATCH)
    assert d.allowed_mode == "draft_patch" and not d.capped and not d.autonomous_write


def test_apply_requires_human_approval() -> None:
    no_appr = guard(task_id="t", requested_mode=ExecutionMode.HUMAN_APPROVED_APPLY,
                    human_approved=False)
    assert no_appr.allowed_mode == "draft_pr" and no_appr.capped
    ok = guard(task_id="t", requested_mode=ExecutionMode.HUMAN_APPROVED_APPLY,
               human_approved=True)
    assert ok.allowed_mode == "human_approved_apply"


def test_autonomous_pr_disabled_by_default() -> None:
    d = guard(task_id="t", requested_mode=ExecutionMode.LOW_RISK_AUTONOMOUS_PR, risk="low")
    assert d.allowed_mode == "draft_pr" and not d.autonomous_write


def test_autonomous_pr_allowed_only_when_policy_and_low_risk() -> None:
    p = GuardrailPolicy(allow_autonomous_pr=True)
    ok = guard(task_id="t", requested_mode=ExecutionMode.LOW_RISK_AUTONOMOUS_PR, risk="low",
               policy=p)
    assert ok.allowed_mode == "low_risk_autonomous_pr" and ok.autonomous_write
    high = guard(task_id="t", requested_mode=ExecutionMode.LOW_RISK_AUTONOMOUS_PR,
                 risk="high", policy=p)
    assert high.allowed_mode == "draft_pr" and not high.autonomous_write


def test_write_mode_capped_without_sandbox_or_trust() -> None:
    no_sandbox = guard(task_id="t", requested_mode=ExecutionMode.HUMAN_APPROVED_APPLY,
                       human_approved=True, sandbox_available=False)
    assert no_sandbox.allowed_mode == "draft_pr"
    untrusted = guard(task_id="t", requested_mode=ExecutionMode.HUMAN_APPROVED_MERGE,
                      human_approved=True, measurement_trusted=False)
    assert untrusted.allowed_mode == "draft_pr"


def test_produce_draft_patch_never_applies(tmp_path, monkeypatch) -> None:
    # a correct proposal -> draft verified in sandbox, but applied/merged stay False
    monkeypatch.chdir(tmp_path)
    draft = produce_draft_patch(DIVIDE, propose=lambda t: t.fixed)
    assert draft.produced and draft.verified_in_sandbox
    assert draft.applied is False and draft.merged is False
    assert draft.diff_lines > 0
    # the cwd must be untouched (no files written by the draft)
    assert not any(tmp_path.iterdir())


def test_produce_draft_patch_records_failed_verification() -> None:
    bad = produce_draft_patch(DIVIDE, propose=lambda t: t.buggy)
    assert bad.produced and not bad.verified_in_sandbox and not bad.applied


def test_no_proposal_yields_unproduced_draft() -> None:
    assert produce_draft_patch(DIVIDE, propose=lambda t: None).produced is False


def test_draft_patch_invariant_dict() -> None:
    d = DraftPatch("t", True, "x", 1, True)
    assert d.to_dict()["applied"] is False
