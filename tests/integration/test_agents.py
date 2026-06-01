"""Agent adapter + registry tests (charter §12)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.agents import (
    ClaudeAgentAdapter,
    CodexAgentAdapter,
    FakeAgentAdapter,
    OpenHandsAgentAdapter,
    PatchAgentAdapter,
    build_default_registry,
)
from acp.core.enums import RunStatus
from acp.schemas.agent import Budget
from acp.schemas.context import ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy


@pytest.fixture
def workspace(tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    (src / "calculator.py").write_text(
        "def divide(a, b):\n    if b == 0:\n        return 0\n    return a / b\n"
    )
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    base = repo.head.commit.hexsha
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    r = Repository(name="d", local_path=str(src))
    snap = RepoSnapshot(repo_id=r.id, base_commit=base)
    return mgr.create(r, snap, default_policy())


def _pack(task_id: str) -> ContextPack:
    return ContextPack(repo_id="r", task_id=task_id, snapshot_id="s")


async def test_registry_register_and_available() -> None:
    reg = build_default_registry(include_external=True)
    assert "fake" in reg.names()
    assert "patch" in reg.names()
    available = await reg.available()
    # fake + patch are always available; external ones gracefully unavailable
    assert "fake" in available
    assert "patch" in available


async def test_unavailable_external_does_not_crash() -> None:
    # Claude/OpenHands have no SDK/key in the test env -> unavailable, no crash.
    for adapter in (ClaudeAgentAdapter(), OpenHandsAgentAdapter()):
        health = await adapter.healthcheck()
        assert health.available is False
        assert health.detail
    # Codex availability depends on a local binary; just assert it never crashes.
    codex_health = await CodexAgentAdapter().healthcheck()
    assert isinstance(codex_health.available, bool)


async def test_fake_execute_captures_diff(workspace) -> None:
    task = Task(repo_id="r", title="t", metadata={"fake_mode": "modify_file",
                "modify": {"new.py": "x = 1\n"}})
    res = await FakeAgentAdapter().execute(task, _pack(task.id), workspace, Budget())
    assert res.status == RunStatus.SUCCEEDED
    assert res.diff is not None
    assert "new.py" in res.diff.changed_files


async def test_fake_timeout_maps_to_timed_out(workspace) -> None:
    task = Task(repo_id="r", title="t", metadata={"fake_mode": "timeout"})
    res = await FakeAgentAdapter().execute(task, _pack(task.id), workspace, Budget())
    assert res.status == RunStatus.TIMED_OUT


async def test_fake_fail_is_structured(workspace) -> None:
    task = Task(repo_id="r", title="t", metadata={"fake_mode": "fail_noop"})
    res = await FakeAgentAdapter().execute(task, _pack(task.id), workspace, Budget())
    assert res.status == RunStatus.FAILED
    assert res.error


async def test_patch_agent_applies_files(workspace) -> None:
    fixed = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"
    task = Task(repo_id="r", title="fix", metadata={"files": {"calculator.py": fixed}})
    res = await PatchAgentAdapter().execute(task, _pack(task.id), workspace, Budget())
    assert res.status == RunStatus.SUCCEEDED
    assert "calculator.py" in res.diff.changed_files
    assert "ZeroDivisionError" in (workspace.path / "calculator.py").read_text()
