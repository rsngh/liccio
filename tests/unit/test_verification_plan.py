"""Verification plan + detector tests (charter §14.1, §14.2)."""

from __future__ import annotations

from pathlib import Path

from acp.core.classifier import classify
from acp.core.enums import TaskType
from acp.schemas.task import Task
from acp.verification.detectors import detect
from acp.verification.plan import build_plan

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/repos/python_buggy_app"


def test_detect_python_pytest() -> None:
    p = detect(FIXTURE)
    assert p.is_python
    assert p.has_pytest
    assert p.test_command == ["python", "-m", "pytest", "-q"]


def test_plan_requires_pytest_for_bugfix() -> None:
    task = Task(repo_id="r", title="Fix divide bug", body="crash on zero")
    cls = classify(task)
    plan = build_plan(task, FIXTURE, cls)
    assert ["python", "-m", "pytest", "-q"] in plan.required_commands


def test_docs_task_no_pytest_required() -> None:
    task = Task(repo_id="r", title="Update docs", body="fix README.md typos")
    cls = classify(task)
    assert cls.task_type == TaskType.DOCS
    plan = build_plan(task, FIXTURE, cls)
    assert plan.required_commands == []


def test_security_task_adds_security_check() -> None:
    task = Task(repo_id="r", title="Fix CVE", body="patch SQL injection vulnerability")
    cls = classify(task)
    plan = build_plan(task, FIXTURE, cls)
    assert any("bandit" in c[0] for c in plan.security_checks)
    assert plan.strategy == "strict"
