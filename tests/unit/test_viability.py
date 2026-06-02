"""Viability assessment (Alpha 7, WS1)."""

from __future__ import annotations

from acp.core.classifier import classify
from acp.core.enums import RiskLevel, TaskType
from acp.core.viability import assess_viability
from acp.schemas.task import Task


def _assess(title: str, body: str = "", **kw) -> object:
    task = Task(repo_id="r", title=title, body=body, **kw)
    return assess_viability(task, classify(task))


def test_docs_task_is_cheap_and_simple_viable() -> None:
    v = _assess("Update README docs", "Fix typos in README.md and docs/guide.md",
                acceptance_criteria=["docs read correctly"])
    assert v.task_type == TaskType.DOCS
    assert v.cheap_model_viable is True
    assert v.true_harness_required is False
    assert "simple_model" in v.viable_agent_classes
    assert not v.abstain


def test_security_task_requires_harness_and_human_review() -> None:
    v = _assess("Fix SQL injection vulnerability in auth",
                "An attacker can exploit a SQL injection in the login path.",
                acceptance_criteria=["injection no longer possible"])
    assert v.task_type == TaskType.SECURITY_FIX
    assert v.true_harness_required is True
    assert v.cheap_model_viable is False
    assert v.human_review_required is True
    assert "acp_harness" in v.viable_agent_classes


def test_no_tests_no_spec_abstains() -> None:
    # No acceptance criteria and a trivial body -> unverifiable -> abstain.
    v = _assess("do the thing", body="")
    assert v.abstain is True
    assert any("unverifiable" in r or "spec" in r for r in v.abstention_reasons)
    assert any(c.name == "spec_inference" for c in v.capability_requirements)


def test_highly_ambiguous_task_abstains_or_reviews() -> None:
    v = _assess("maybe improve various things somehow etc",
                "improve various stuff, make it better somehow, misc cleanup etc")
    assert v.ambiguity_score > 0.5
    assert v.human_review_required or v.abstain


def test_bugfix_prefers_reproduction_strategies() -> None:
    v = _assess("Fix crash in divide", "divide() crashes on zero; fix calculator.py",
                acceptance_criteria=["divide(x,0) raises"])
    assert v.task_type == TaskType.BUGFIX
    assert "bug_reproduction" in v.viable_context_strategies
    assert v.confidence > 0.0


def test_supporting_features_and_summary() -> None:
    v = _assess("Fix bug in parser", "parser.py mishandles input",
                acceptance_criteria=["parses correctly"])
    assert "ambiguity" in v.supporting_features
    assert "testability" in v.supporting_features
    assert isinstance(v.summary(), str)
    assert v.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
