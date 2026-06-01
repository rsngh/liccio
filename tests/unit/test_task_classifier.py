"""Task classifier tests (charter §11)."""

from __future__ import annotations

from acp.core.classifier import classify
from acp.core.enums import RiskLevel, TaskType
from acp.schemas.task import Task


def _t(title: str, body: str = "", **kw) -> Task:
    return Task(repo_id="r", title=title, body=body, **kw)


def test_docs_only_low_risk() -> None:
    c = classify(_t("Update README.md", "fix typos in docs/guide.md"))
    assert c.task_type == TaskType.DOCS
    assert c.risk_level == RiskLevel.LOW


def test_auth_change_high_risk() -> None:
    c = classify(_t("Refactor login auth flow", "change password hashing in auth module"))
    assert c.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert c.human_review_required is True


def test_cve_security_fix() -> None:
    c = classify(_t("Patch CVE-2024-1234", "fix SQL injection vulnerability"))
    assert c.task_type == TaskType.SECURITY_FIX
    assert c.risk_level == RiskLevel.CRITICAL


def test_failing_test_is_bug_or_ci() -> None:
    c = classify(_t("Fix failing test", "pytest traceback in test_calc, build fails"))
    assert c.task_type in (TaskType.BUGFIX, TaskType.CI_FIX)


def test_vague_feature_high_ambiguity() -> None:
    c = classify(_t("Improve things", "maybe make it better somehow"))
    assert c.ambiguity_score > 0.7


def test_acceptance_criteria_lowers_ambiguity() -> None:
    vague = classify(_t("Add feature", "implement export"))
    precise = classify(
        _t("Add feature", "implement export", acceptance_criteria=["CSV export works", "tested"])
    )
    assert precise.ambiguity_score < vague.ambiguity_score


def test_required_verification_for_bugfix() -> None:
    c = classify(_t("Fix bug", "crash on empty input"))
    assert "unit_test" in c.required_verification_kinds
