"""Verification plan generation (charter §14.1)."""

from __future__ import annotations

from pathlib import Path

from acp.core.enums import RiskLevel, TaskType
from acp.schemas.task import Task, TaskClassification
from acp.schemas.verification import VerificationPlan
from acp.verification.detectors import ProjectProfile, detect


def build_plan(
    task: Task,
    workspace_path: Path | str,
    classification: TaskClassification | None = None,
    profile: ProjectProfile | None = None,
) -> VerificationPlan:
    profile = profile or detect(workspace_path)
    risk = classification.risk_level if classification else task.risk_level
    if isinstance(risk, str):
        risk = RiskLevel(risk)

    required: list[list[str]] = []
    optional: list[list[str]] = []
    static: list[list[str]] = []
    security: list[list[str]] = []
    coverage: list[list[str]] = []

    task_type = classification.task_type if classification else task.task_type

    # Docs-only tasks do not require pytest by default (charter §14.6).
    if task_type != TaskType.DOCS and profile.has_pytest and profile.test_command:
        required.append(profile.test_command)

    if profile.lint_command:
        static.append(profile.lint_command)
    if profile.typecheck_command:
        static.append(profile.typecheck_command)
    if profile.playwright:
        optional.append(["npx", "playwright", "test"])

    if task_type == TaskType.SECURITY_FIX or risk.requires_human_review():
        security.append(["bandit", "-r", "."])

    if task_type in (TaskType.BUGFIX, TaskType.CI_FIX) and profile.has_pytest:
        coverage.append(["python", "-m", "pytest", "--cov", "-q"])

    return VerificationPlan(
        task_id=task.id,
        strategy="strict" if risk.requires_human_review() else "standard",
        required_commands=required,
        optional_commands=optional,
        static_checks=static,
        security_checks=security,
        coverage_checks=coverage,
        acceptance_assertions=task.acceptance_criteria,
        risk_level=risk,
    )
