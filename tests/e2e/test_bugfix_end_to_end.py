"""End-to-end orchestration tests (charter §17.4, §20, §26)."""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from acp.agents.fake import FakeAgentAdapter
from acp.agents.patch_agent import PatchAgentAdapter
from acp.agents.registry import AgentRegistry
from acp.core.enums import HumanVerdict, RunStatus
from acp.orchestration.runner import WorkflowRunner
from acp.schemas.human_review import HumanLabel
from acp.schemas.repo import Repository
from acp.schemas.task import Task

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/repos/python_buggy_app"

FIXED_CALC = (
    "def add(a, b):\n    return a + b\n\n\n"
    "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError('division by zero')\n"
    "    return a / b\n"
)


def _make_repo(tmp_path) -> Repository:
    dst = tmp_path / "repo"
    dst.mkdir()
    for rel in ["pyproject.toml", "src/calculator.py", "tests/test_calculator.py", "AGENTS.md"]:
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text((FIXTURE / rel).read_text())
    repo = Repo.init(dst)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["pyproject.toml", "src/calculator.py", "tests/test_calculator.py", "AGENTS.md"])
    repo.index.commit("init")
    return Repository(name="buggy", local_path=str(dst), default_branch="master")


@pytest.fixture
def patch_registry() -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(PatchAgentAdapter())
    reg.register(FakeAgentAdapter())
    return reg


async def test_bugfix_full_loop_succeeds(tmp_path, patch_registry) -> None:
    repo = _make_repo(tmp_path)
    runner = WorkflowRunner(repo, patch_registry, tmp_path / "ws")
    task = Task(
        repo_id=repo.id,
        title="Fix divide by zero",
        body="divide() returns 0 on zero divisor; must raise ZeroDivisionError",
        acceptance_criteria=["divide(x,0) raises ZeroDivisionError"],
        metadata={"files": {"src/calculator.py": FIXED_CALC}},
    )
    state = await runner.run(task)

    assert state.status == RunStatus.SUCCEEDED
    # full provenance chain exists (charter §26.3)
    assert state.snapshot_id
    assert state.context_pack_id
    assert state.routing_decision_id
    assert state.attempt_ids
    assert state.selected_attempt_id
    assert state.evaluation_result_id
    assert state.reward_event_id
    assert state.trace_id
    # routing logged a probability (charter §26.6)
    assert runner.artifacts.routing_decision.action_probability > 0
    # reward components stored
    assert runner.artifacts.reward.components


async def test_fake_failure_fails_run(tmp_path, patch_registry) -> None:
    repo = _make_repo(tmp_path)
    runner = WorkflowRunner(repo, patch_registry, tmp_path / "ws")
    task = Task(repo_id=repo.id, title="x", body="y",
                metadata={"fake_mode": "fail_noop"})
    # force the fake agent via routing fallback by removing patch
    reg = AgentRegistry()
    reg.register(FakeAgentAdapter(mode="fail_noop"))
    runner = WorkflowRunner(repo, reg, tmp_path / "ws2")
    state = await runner.run(task)
    assert state.status == RunStatus.FAILED


async def test_high_risk_pauses_for_human_then_resumes(tmp_path, patch_registry) -> None:
    repo = _make_repo(tmp_path)
    runner = WorkflowRunner(repo, patch_registry, tmp_path / "ws")
    task = Task(
        repo_id=repo.id,
        title="Update auth password hashing",
        body="change login auth to use bcrypt",
        metadata={"files": {"src/calculator.py": FIXED_CALC}},
    )
    state = await runner.run(task)
    assert state.status == RunStatus.WAITING_FOR_HUMAN
    assert state.human_review_item_id

    label = HumanLabel(
        review_item_id=state.human_review_item_id, task_id=task.id,
        verdict=HumanVerdict.PASS, score=0.9, reason="looks good",
    )
    resumed = await runner.resume(state, label)
    assert resumed.status == RunStatus.SUCCEEDED
    assert resumed.reward_event_id


async def test_human_reject_fails_run(tmp_path, patch_registry) -> None:
    repo = _make_repo(tmp_path)
    runner = WorkflowRunner(repo, patch_registry, tmp_path / "ws")
    task = Task(repo_id=repo.id, title="Refactor billing crypto",
                body="touch payment crypto module",
                metadata={"files": {"src/calculator.py": FIXED_CALC}})
    state = await runner.run(task)
    assert state.status == RunStatus.WAITING_FOR_HUMAN
    label = HumanLabel(review_item_id=state.human_review_item_id, task_id=task.id,
                       verdict=HumanVerdict.FAIL, reason="unsafe")
    resumed = await runner.resume(state, label)
    assert resumed.status == RunStatus.FAILED


async def test_multiple_attempts_isolated_workspaces(tmp_path, patch_registry) -> None:
    # primary (patch) + fallback (fake) -> two attempts in two distinct workspaces
    repo = _make_repo(tmp_path)
    runner = WorkflowRunner(repo, patch_registry, tmp_path / "ws")
    task = Task(repo_id=repo.id, title="Fix divide bug", body="zero divisor bug",
                metadata={"files": {"src/calculator.py": FIXED_CALC}})
    state = await runner.run(task)
    assert len(state.attempt_ids) >= 2
    ws_paths = set(state.scratch["workspaces"].values())
    assert len(ws_paths) == len(state.attempt_ids)  # isolated workspaces


async def test_resume_is_idempotent(tmp_path, patch_registry) -> None:
    repo = _make_repo(tmp_path)
    runner = WorkflowRunner(repo, patch_registry, tmp_path / "ws")
    task = Task(repo_id=repo.id, title="Fix divide bug", body="zero divisor",
                metadata={"files": {"src/calculator.py": FIXED_CALC}})
    state = await runner.run(task)
    completed_before = list(state.completed_nodes)
    # resuming a finished run does not rerun nodes
    again = await runner.resume(state)
    assert again.completed_nodes == completed_before
