"""Vendor activation vs task failure must be distinguishable (Alpha 26 measurement-trust).

A no-op vendor run (the CLI returns without editing anything — e.g. degraded/rate-limited)
must classify as a HARNESS-ACTIVATION failure, NOT a task/skill capability failure. This is
what lets the vendor corpus guard refuse to read a no-activation arm as negative transfer.
"""

from __future__ import annotations

from acp.agents.vendor_native import VendorRunResult
from acp.evaluation.measurement_hygiene import classify_attempt


def _cell(*, solved, diff):
    r = VendorRunResult(harness="claude_code", version="v", task_type="hard")
    r.no_patch_solve = solved
    r.pytest_passed = solved
    r.diff_captured = diff
    r.timed_out = False
    r.error = None
    return r.to_cell()


def test_no_diff_no_solve_is_activation_failure_not_task_failure() -> None:
    outcome = classify_attempt(_cell(solved=False, diff=False))
    assert outcome.value == "harness_activation_failure"
    assert not outcome.is_success


def test_real_edit_that_fails_is_a_task_failure() -> None:
    # the harness DID work (produced a diff) but the edit was wrong -> conclusive task failure
    outcome = classify_attempt(_cell(solved=False, diff=True))
    assert outcome.value == "task_failure"


def test_solved_is_success_regardless_of_diff_flag() -> None:
    assert classify_attempt(_cell(solved=True, diff=True)).is_success


def test_activation_distinguishes_infra_from_capability() -> None:
    # an activation failure (no work) must never be read as the model failing the task
    act = classify_attempt(_cell(solved=False, diff=False))
    fail = classify_attempt(_cell(solved=False, diff=True))
    assert act != fail  # the two are different outcomes
