"""End-to-end verification run against the bugfix fixture (charter §14)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from git import Repo

from acp.core.enums import EvidenceStatus
from acp.schemas.task import Task
from acp.verification.plan import build_plan
from acp.verification.service import VerificationService
from acp.workspaces.command_runner import CommandRunner

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/repos/python_buggy_app"


@pytest.fixture
def workspace(tmp_path) -> Path:
    dst = tmp_path / "repo"
    dst.mkdir()
    # copy fixture files
    for rel in ["pyproject.toml", "src/calculator.py", "tests/test_calculator.py", "AGENTS.md"]:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((FIXTURE / rel).read_text())
    repo = Repo.init(dst)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["pyproject.toml", "src/calculator.py", "tests/test_calculator.py", "AGENTS.md"])
    repo.index.commit("init")
    return dst


def test_pytest_passes_on_green_fixture(workspace: Path) -> None:
    # fixture tests are green as-is (they don't assert the zero-division behavior)
    task = Task(repo_id="r", title="Fix divide", body="bug")
    plan = build_plan(task, workspace)
    # force the venv python so pytest is available
    plan.required_commands = [[sys.executable, "-m", "pytest", "-q"]]
    runner = CommandRunner(allowed_root=workspace)
    run, evidence = VerificationService(runner).run_plan(plan, workspace, attempt_id="a1")
    pytest_ev = next(e for e in evidence if e.name == "pytest")
    assert pytest_ev.status == EvidenceStatus.PASS
    assert pytest_ev.metadata["passed"] >= 2


def test_pytest_fails_when_test_broken(workspace: Path) -> None:
    (workspace / "tests" / "test_calculator.py").write_text(
        "def test_zero():\n    assert False\n"
    )
    task = Task(repo_id="r", title="x", body="y")
    plan = build_plan(task, workspace)
    plan.required_commands = [[sys.executable, "-m", "pytest", "-q"]]
    runner = CommandRunner(allowed_root=workspace)
    _run, evidence = VerificationService(runner).run_plan(plan, workspace, attempt_id="a2")
    pytest_ev = next(e for e in evidence if e.name == "pytest")
    assert pytest_ev.status == EvidenceStatus.FAIL


def test_missing_command_marks_skipped(workspace: Path) -> None:
    task = Task(repo_id="r", title="x", body="y")
    plan = build_plan(task, workspace)
    plan.required_commands = [["definitely-not-real-binary-xyz", "--run"]]
    runner = CommandRunner(allowed_root=workspace)
    _run, evidence = VerificationService(runner).run_plan(plan, workspace)
    assert evidence[0].status == EvidenceStatus.SKIPPED
