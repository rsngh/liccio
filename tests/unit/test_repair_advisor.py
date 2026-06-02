"""Repair-driven retry advisor (Alpha 9)."""

from __future__ import annotations

from acp.core.repair_advisor import RepairAdvisor, repair_strategies
from acp.schemas.task import Task


def _advise(title, body, failure="", **kw):
    return RepairAdvisor().advise(Task(repo_id="r", title=title, body=body, **kw),
                                  failure_output=failure)


def test_dependency_failure_recommends_retryable_plan() -> None:
    a = _advise("Fix import", "module broken",
                failure="ModuleNotFoundError: No module named 'requests'")
    assert a.repair_strategy == "dependency_update"
    assert a.retryable is True


def test_needs_spec_escalates_and_not_retryable() -> None:
    a = _advise("do something", "")
    assert a.repair_strategy == "needs_spec"
    assert a.escalate_to_human is True
    assert a.retryable is False


def test_security_requires_harness_and_human() -> None:
    a = _advise("Fix SQL injection in auth", "attacker injects sql in login",
                acceptance_criteria=["blocked"])
    assert a.repair_strategy == "security_remediation"
    assert a.true_harness_required is True
    assert a.escalate_to_human is True


def test_advice_always_has_known_strategy_and_reasons() -> None:
    a = _advise("Fix crash", "AssertionError in test_foo", acceptance_criteria=["x"])
    assert a.repair_strategy in repair_strategies()
    assert a.reasons
    assert a.recommended_context_strategy
