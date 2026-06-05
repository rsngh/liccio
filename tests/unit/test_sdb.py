"""Stochastic–deterministic boundary (SDB) contracts (Alpha 24 area 8)."""

from __future__ import annotations

import pytest

from acp.orchestration.sdb import (
    PartialResultPolicy,
    Proposal,
    SDBContract,
    VerificationResult,
    run_contract,
)


def _pass(name):
    return lambda p: VerificationResult(name=name, passed=True)


def _fail(name, reason):
    return lambda p: VerificationResult(name=name, passed=False, reject_reason=reason)


def test_all_pass_commits() -> None:
    c = SDBContract("code_patch", [_pass("pytest"), _pass("diff_minimal")])
    rec = run_contract(c, Proposal("code_patch", proposer="gpt-4o-mini"))
    assert rec.committed and not rec.reject_reasons


def test_any_fail_rejects_with_typed_reason() -> None:
    c = SDBContract("skill_edit", [_pass("schema"), _fail("gain", "no_measured_gain")])
    rec = run_contract(c, Proposal("skill_edit"))
    assert not rec.committed and rec.reject_reasons == ["no_measured_gain"]


def test_poison_blocks_commit() -> None:
    c = SDBContract("harness_patch", [_fail("poison_scan", "poison_detected")])
    rec = run_contract(c, Proposal("harness_patch"))
    assert not rec.committed and "poison_detected" in rec.reject_reasons


def test_deadline_partial_rejects_by_default() -> None:
    c = SDBContract("code_patch", [_pass("pytest")])
    rec = run_contract(c, Proposal("code_patch"), deadline_hit=True)
    assert rec.partial and not rec.committed and rec.reject_reasons == ["deadline_partial"]


def test_deadline_commit_partial_policy() -> None:
    c = SDBContract("context_update", [_pass("x")],
                    PartialResultPolicy(on_deadline="commit_partial"))
    rec = run_contract(c, Proposal("context_update"), deadline_hit=True)
    assert rec.partial and rec.committed


def test_failed_verifier_requires_typed_reason() -> None:
    with pytest.raises(ValueError):
        VerificationResult(name="x", passed=False)  # no reject_reason


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValueError):
        Proposal("delete_prod_db")


def test_contract_kind_must_match_proposal() -> None:
    c = SDBContract("memory_write", [_pass("x")])
    with pytest.raises(ValueError):
        run_contract(c, Proposal("code_patch"))
