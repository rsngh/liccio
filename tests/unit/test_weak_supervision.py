"""Weak supervision tests (charter §15.2)."""

from __future__ import annotations

from acp.core.enums import WeakLabelValue
from acp.evaluation.weak_supervision import default_supervisor


def _label(features):
    return default_supervisor().label(features, task_id="t", attempt_id="a")


def test_ci_pass_small_diff_success() -> None:
    wl = _label({"ci_passed": True, "tests_failed": False, "diff_churn": 10, "changed_files": 1})
    assert wl.label == WeakLabelValue.SUCCESS


def test_pass_but_no_bugfix_test_suspicious() -> None:
    wl = _label({"task_type": "bugfix", "touches_tests": False})
    assert wl.label == WeakLabelValue.SUSPICIOUS


def test_security_warning_needs_review() -> None:
    wl = _label({"security_high": True})
    assert wl.label == WeakLabelValue.NEEDS_REVIEW


def test_revert_failure() -> None:
    wl = _label({"reverted": True})
    assert wl.label == WeakLabelValue.FAILURE


def test_parallel_disagreement_needs_review() -> None:
    wl = _label({"parallel_disagreement": True})
    assert wl.label == WeakLabelValue.NEEDS_REVIEW


def test_probabilities_sum_to_one() -> None:
    wl = _label({"ci_passed": True, "security_high": True})
    assert abs(sum(wl.probabilities.values()) - 1.0) < 1e-6
