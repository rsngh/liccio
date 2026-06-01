"""Weak supervision engine (charter §15.2).

A set of labeling functions each emit a WeakSignal; signals are aggregated into a
probabilistic WeakLabel. Signals operate over a feature dict assembled from the
attempt, evidence, diff, and outcome.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from acp.core.enums import WeakLabelValue
from acp.schemas.evaluation import WeakLabel, WeakSignal

LabelingFn = Callable[[dict[str, Any]], WeakSignal | None]


@dataclass
class WeakSupervisor:
    labeling_functions: list[LabelingFn] = field(default_factory=list)

    def label(
        self, features: dict[str, Any], task_id: str, attempt_id: str | None = None
    ) -> WeakLabel:
        signals = [s for lf in self.labeling_functions if (s := lf(features)) is not None]
        return aggregate_signals(signals, task_id, attempt_id)


def aggregate_signals(
    signals: list[WeakSignal], task_id: str, attempt_id: str | None = None
) -> WeakLabel:
    """Confidence-weighted vote over signals -> probability per label."""
    weights: dict[str, float] = {v.value: 0.0 for v in WeakLabelValue}
    for s in signals:
        key = s.label.value if hasattr(s.label, "value") else str(s.label)
        weights[key] += s.confidence
    total = sum(weights.values()) or 1.0
    probs = {k: round(v / total, 4) for k, v in weights.items()}
    # Decide label, ignoring 'unknown' unless nothing else fired.
    ranked = sorted(
        ((k, v) for k, v in probs.items() if k != "unknown"), key=lambda kv: kv[1], reverse=True
    )
    best, best_p = (ranked[0] if ranked and ranked[0][1] > 0 else ("unknown", probs["unknown"]))
    return WeakLabel(
        task_id=task_id,
        attempt_id=attempt_id,
        label=WeakLabelValue(best),
        probabilities=probs,
        confidence=round(best_p, 4),
        signals=signals,
    )


# ---- labeling functions (charter §15.2) ----------------------------------


def _sig(name: str, label: WeakLabelValue, conf: float, reason: str) -> WeakSignal:
    return WeakSignal(name=name, label=label, confidence=conf, reason=reason)


def ci_passed_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("ci_passed") is True:
        return _sig("ci_passed", WeakLabelValue.SUCCESS, 0.7, "CI passed")
    return None


def tests_failed_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("tests_failed"):
        return _sig("tests_failed", WeakLabelValue.FAILURE, 0.9, "tests failed")
    return None


def new_regression_test_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("added_regression_test"):
        return _sig("new_regression_test", WeakLabelValue.SUCCESS, 0.4, "added regression test")
    return None


def no_test_for_bugfix_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("task_type") in ("bugfix", "ci_fix") and not f.get("touches_tests", True):
        return _sig("no_test_for_bugfix", WeakLabelValue.SUSPICIOUS, 0.6, "bugfix without tests")
    return None


def large_diff_signal(f: dict[str, Any]) -> WeakSignal | None:
    if (f.get("diff_churn", 0) > 400) or (f.get("changed_files", 0) > 15):
        return _sig("large_diff", WeakLabelValue.NEEDS_REVIEW, 0.5, "large diff")
    return None


def sensitive_module_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("touches_sensitive"):
        return _sig("sensitive_module", WeakLabelValue.NEEDS_REVIEW, 0.7, "sensitive module")
    return None


def unrelated_files_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("unrelated_files"):
        return _sig("unrelated_files", WeakLabelValue.SUSPICIOUS, 0.5, "unrelated files changed")
    return None


def security_warning_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("security_high"):
        return _sig("security_warning", WeakLabelValue.NEEDS_REVIEW, 0.8, "security high severity")
    return None


def reviewer_approved_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("reviewer_approved"):
        return _sig("reviewer_approved", WeakLabelValue.SUCCESS, 0.9, "reviewer approved")
    return None


def reviewer_requested_changes_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("reviewer_requested_changes"):
        return _sig("reviewer_requested_changes", WeakLabelValue.FAILURE, 0.7, "changes requested")
    return None


def post_merge_revert_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("reverted"):
        return _sig("post_merge_revert", WeakLabelValue.FAILURE, 0.95, "reverted post-merge")
    return None


def production_incident_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("incident"):
        return _sig("production_incident", WeakLabelValue.FAILURE, 0.95, "production incident")
    return None


def agent_timeout_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("agent_timeout"):
        return _sig("agent_timeout", WeakLabelValue.FAILURE, 0.6, "agent timed out")
    return None


def budget_overrun_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("budget_overrun"):
        return _sig("budget_overrun", WeakLabelValue.SUSPICIOUS, 0.4, "budget overrun")
    return None


def parallel_disagreement_signal(f: dict[str, Any]) -> WeakSignal | None:
    if f.get("parallel_disagreement"):
        return _sig(
            "parallel_disagreement", WeakLabelValue.NEEDS_REVIEW, 0.6, "parallel attempts disagree"
        )
    return None


DEFAULT_LABELING_FUNCTIONS: list[LabelingFn] = [
    ci_passed_signal,
    tests_failed_signal,
    new_regression_test_signal,
    no_test_for_bugfix_signal,
    large_diff_signal,
    sensitive_module_signal,
    unrelated_files_signal,
    security_warning_signal,
    reviewer_approved_signal,
    reviewer_requested_changes_signal,
    post_merge_revert_signal,
    production_incident_signal,
    agent_timeout_signal,
    budget_overrun_signal,
    parallel_disagreement_signal,
]


def default_supervisor() -> WeakSupervisor:
    return WeakSupervisor(labeling_functions=list(DEFAULT_LABELING_FUNCTIONS))
