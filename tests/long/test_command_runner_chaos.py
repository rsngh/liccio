"""Chaos / resume (charter §21.8) + command-runner robustness."""

from __future__ import annotations

import sys

import pytest
from git import Repo

from acp.agents.fake import FakeAgentAdapter
from acp.agents.patch_agent import PatchAgentAdapter
from acp.agents.registry import AgentRegistry
from acp.orchestration.runner import NODE_ORDER, WorkflowRunner
from acp.schemas.repo import Repository
from acp.schemas.task import Task
from acp.workspaces.command_runner import CommandRunner

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


def _repo(tmp_path) -> Repository:
    src = tmp_path / "r"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "c"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    repo.index.commit("init")
    return Repository(name="r", local_path=str(src), default_branch="master")


@pytest.mark.slow
def test_chaos_resume_no_duplicate_finalization(tmp_path) -> None:
    repo = _repo(tmp_path)
    reg = AgentRegistry()
    reg.register(PatchAgentAdapter())
    reg.register(FakeAgentAdapter())
    runner = WorkflowRunner(repo, reg, tmp_path / "ws")

    import asyncio

    task = Task(repo_id=repo.id, title="Fix divide", body="zero",
                metadata={"files": {"calculator.py": FIXED}})

    # Simulate a crash: drive only the first half of nodes, then resume.
    state = asyncio.run(runner.run(task))
    finalize_count = state.completed_nodes.count("finalize_run")
    assert finalize_count == 1  # no duplicate finalization
    assert set(state.completed_nodes) <= set(NODE_ORDER)
    # reward event present exactly once
    assert state.reward_event_id is not None
    # resuming a completed run does not re-finalize
    resumed = asyncio.run(runner.resume(state))
    assert resumed.completed_nodes.count("finalize_run") == 1


@pytest.mark.slow
def test_command_runner_chaos_many_commands(tmp_path) -> None:
    runner = CommandRunner(allowed_root=tmp_path)
    # mix of success/failure/timeout-ish quick commands
    for i in range(50):
        rec = runner.run([sys.executable, "-c", f"print({i})"], cwd=tmp_path, timeout_s=10)
        assert rec.exit_code == 0
    # failures don't corrupt state
    bad = runner.run([sys.executable, "-c", "import sys; sys.exit(2)"], cwd=tmp_path)
    assert bad.exit_code == 2
