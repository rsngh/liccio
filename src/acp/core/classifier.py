"""Deterministic task classifier (charter §11).

Rule-based: maps task text/labels/paths to task_type, risk_level, ambiguity,
testability, and required verification kinds. No ML, fully deterministic.
"""

from __future__ import annotations

import re

from acp.core.enums import EvidenceKind, RiskLevel, TaskType
from acp.schemas.task import Task, TaskClassification

_SECURITY = re.compile(r"\b(cve|vulnerab|exploit|injection|xss|csrf|rce|security)\b", re.I)
_DEP = re.compile(r"\b(dependenc|bump|upgrade package|requirements\.txt|package\.json)\b", re.I)
_CI = re.compile(r"\b(ci|pipeline|failing test|traceback|stack ?trace|build fail)\b", re.I)
_BUG = re.compile(r"\b(bug|fix|broken|incorrect|crash|error|regression)\b", re.I)
_REFACTOR = re.compile(r"\b(refactor|rename|cleanup|restructure)\b", re.I)
_MIGRATION = re.compile(r"\b(migrat|schema change|alembic|upgrade db)\b", re.I)
_TESTGEN = re.compile(r"\b(add tests?|write tests?|test coverage)\b", re.I)
_FEATURE = re.compile(r"\b(add|implement|support|feature|new endpoint)\b", re.I)
_SENSITIVE = re.compile(
    r"\b(auth|login|password|billing|payment|crypto|permission|delete data|token|secret)\b",
    re.I,
)
_VAGUE = re.compile(r"\b(maybe|somehow|etc|various|improve|better|clean up|misc)\b", re.I)


def classify(task: Task) -> TaskClassification:
    text = f"{task.title}\n{task.body}\n{' '.join(task.labels)}"
    paths = _mentioned_paths(text)
    reasons: list[str] = []

    task_type = _infer_type(text, paths, reasons)
    risk = _infer_risk(text, task_type, reasons)
    ambiguity = _ambiguity(task, text, reasons)
    testability = _testability(task_type, paths)
    verification = _verification_kinds(task_type)
    human = risk.requires_human_review() or ambiguity > 0.7

    return TaskClassification(
        task_type=task_type,
        risk_level=risk,
        ambiguity_score=round(ambiguity, 3),
        testability_score=round(testability, 3),
        affected_modules_estimate=len({p.split("/")[0] for p in paths}) or 1,
        required_verification_kinds=[k.value for k in verification],
        human_review_required=human,
        reasons=reasons,
    )


def _mentioned_paths(text: str) -> list[str]:
    return re.findall(r"[\w./-]+\.(?:py|js|ts|tsx|md|toml|json|yaml|yml|cfg)", text)


def _infer_type(text: str, paths: list[str], reasons: list[str]) -> TaskType:
    docs_only = bool(paths) and all(
        p.lower().endswith((".md", ".rst", ".txt")) for p in paths
    )
    docs_kw = re.search(r"\b(docs?|documentation|readme)\b", text, re.I) is not None
    if docs_only or (docs_kw and not paths):
        reasons.append("documentation-only task")
        return TaskType.DOCS
    if _SECURITY.search(text):
        reasons.append("security keywords")
        return TaskType.SECURITY_FIX
    if _DEP.search(text):
        reasons.append("dependency keywords")
        return TaskType.DEPENDENCY_UPDATE
    if _MIGRATION.search(text):
        reasons.append("migration keywords")
        return TaskType.MIGRATION
    if _CI.search(text):
        reasons.append("CI/traceback keywords")
        return TaskType.CI_FIX
    if _TESTGEN.search(text):
        reasons.append("test-generation keywords")
        return TaskType.TEST_GENERATION
    if _REFACTOR.search(text):
        reasons.append("refactor keywords")
        return TaskType.REFACTOR
    if _BUG.search(text):
        reasons.append("bug keywords")
        return TaskType.BUGFIX
    if _FEATURE.search(text):
        reasons.append("feature keywords")
        return TaskType.FEATURE
    return TaskType.UNKNOWN


def _infer_risk(text: str, task_type: TaskType, reasons: list[str]) -> RiskLevel:
    if task_type == TaskType.SECURITY_FIX:
        reasons.append("security fixes are critical risk")
        return RiskLevel.CRITICAL
    if _SENSITIVE.search(text):
        reasons.append("touches sensitive area (auth/billing/crypto/perms/data)")
        return RiskLevel.HIGH
    if task_type == TaskType.MIGRATION:
        return RiskLevel.HIGH
    if task_type == TaskType.DOCS:
        return RiskLevel.LOW
    if task_type in (TaskType.TEST_GENERATION, TaskType.DEPENDENCY_UPDATE):
        return RiskLevel.LOW
    return RiskLevel.MEDIUM


def _ambiguity(task: Task, text: str, reasons: list[str]) -> float:
    score = 0.5
    if task.acceptance_criteria:
        score -= 0.35
        reasons.append("explicit acceptance criteria lower ambiguity")
    else:
        score += 0.2
        reasons.append("no acceptance criteria")
    if _VAGUE.search(text):
        score += 0.25
        reasons.append("vague terms present")
    if len(task.body) < 30:
        score += 0.1
    return max(0.0, min(1.0, score))


def _testability(task_type: TaskType, paths: list[str]) -> float:
    if task_type in (TaskType.BUGFIX, TaskType.CI_FIX, TaskType.TEST_GENERATION):
        return 0.9
    if task_type == TaskType.DOCS:
        return 0.2
    if task_type in (TaskType.FEATURE, TaskType.REFACTOR):
        return 0.6
    return 0.5


def _verification_kinds(task_type: TaskType) -> list[EvidenceKind]:
    if task_type == TaskType.DOCS:
        return [EvidenceKind.LINT]
    base = [EvidenceKind.UNIT_TEST, EvidenceKind.LINT, EvidenceKind.TYPE_CHECK]
    if task_type == TaskType.SECURITY_FIX:
        base.append(EvidenceKind.SECURITY_SCAN)
    if task_type in (TaskType.BUGFIX, TaskType.CI_FIX):
        base.append(EvidenceKind.COVERAGE)
    return base
