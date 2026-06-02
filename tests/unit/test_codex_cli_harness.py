"""Codex CLI vendor harness tests (alpha-7 WS8).

Exercises the real (but safe) codex vendor harness loop without ever invoking a
real ``codex`` process or network. Availability and the CommandRunner are forced
via monkeypatching / dependency injection so the tests are deterministic even if
a real ``codex`` binary is present on PATH.
"""

from __future__ import annotations

import pytest
from git import Repo

from acp.agents import codex_cli as codex_mod
from acp.agents.codex_cli import CodexCLIAdapter
from acp.agents.trace import build_agent_trace
from acp.agents.vendor_base import VendorHarnessAdapter
from acp.core.enums import AgentKind, RunStatus
from acp.core.time import utcnow
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.schemas.workspace import CommandRunRecord
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy


@pytest.fixture
def workspace(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    return mgr.create(
        r,
        RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
        default_policy(),
    )


def _task() -> Task:
    return Task(repo_id="r", title="fix divide", body="make divide actually divide")


def _ctx() -> ContextPack:
    return ContextPack(repo_id="r", task_id="t", snapshot_id="s")


class _FakeRunner:
    """Stand-in CommandRunner that records the argv and returns a canned record."""

    def __init__(self, *, timed_out: bool = False, exit_code: int | None = 0) -> None:
        self.timed_out = timed_out
        self.exit_code = exit_code
        self.calls: list[tuple[list[str], int | None]] = []

    def run(self, command, cwd, timeout_s=None, **kwargs) -> CommandRunRecord:
        self.calls.append((command, timeout_s))
        return CommandRunRecord(
            argv=command,
            cwd=str(cwd),
            exit_code=None if self.timed_out else self.exit_code,
            timed_out=self.timed_out,
            stdout_summary="",
            stderr_summary="boom" if self.exit_code not in (0, None) else "",
        )


def test_adapter_is_vendor_harness() -> None:
    adapter = CodexCLIAdapter()
    assert adapter.is_harness is True
    assert adapter.category == "vendor"
    assert adapter.kind == AgentKind.CODEX
    assert isinstance(adapter, VendorHarnessAdapter)


def test_build_command_is_workspace_scoped_and_noninteractive(workspace) -> None:
    adapter = CodexCLIAdapter()
    command = adapter.build_command(_task(), _ctx(), workspace)
    assert command[0] == "codex"
    # Non-interactive headless subcommand.
    assert "exec" in command
    # Scoped to the workspace path.
    assert str(workspace.path) in command
    assert any(str(workspace.path) in arg for arg in command)


@pytest.mark.asyncio
async def test_unavailable_returns_clean_result(monkeypatch, workspace) -> None:
    """codex binary forced absent -> clean failed result, no raise."""
    monkeypatch.setattr(
        CodexCLIAdapter, "_requirement_present", lambda self: False
    )
    adapter = CodexCLIAdapter()
    assert adapter.available() is False
    result = await adapter.execute(_task(), _ctx(), workspace, Budget())
    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert "unavailable" in result.error
    assert result.metadata.get("category") == "vendor"
    assert result.metadata.get("available") is False


@pytest.mark.asyncio
async def test_timeout_returns_timed_out_without_raising(monkeypatch, workspace) -> None:
    """A simulated timeout from the runner -> TIMED_OUT, timeout-ish error, no raise."""
    monkeypatch.setattr(CodexCLIAdapter, "_requirement_present", lambda self: True)
    runner = _FakeRunner(timed_out=True)
    adapter = CodexCLIAdapter()
    monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)

    result = await adapter.execute(_task(), _ctx(), workspace, Budget(max_wall_time_s=5))

    assert result.status == RunStatus.TIMED_OUT
    assert result.error == "timeout"
    # The runner was called with the budget-derived wall-time timeout.
    assert runner.calls and runner.calls[0][1] == 5
    # argv was workspace-scoped.
    assert str(workspace.path) in runner.calls[0][0]


@pytest.mark.asyncio
async def test_nonzero_exit_is_failed(monkeypatch, workspace) -> None:
    monkeypatch.setattr(CodexCLIAdapter, "_requirement_present", lambda self: True)
    runner = _FakeRunner(exit_code=1)
    adapter = CodexCLIAdapter()
    monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)

    result = await adapter.execute(_task(), _ctx(), workspace, Budget())

    assert result.status == RunStatus.FAILED
    assert result.error is not None and "exited 1" in result.error


@pytest.mark.asyncio
async def test_success_when_exit0_and_diff(monkeypatch, workspace) -> None:
    """exit 0 + a produced diff -> SUCCEEDED. The fake runner writes the diff."""
    monkeypatch.setattr(CodexCLIAdapter, "_requirement_present", lambda self: True)

    class _DiffWritingRunner(_FakeRunner):
        def run(self, command, cwd, timeout_s=None, **kwargs):
            (workspace.path / "calculator.py").write_text(
                "def divide(a, b):\n    return a / b\n"
            )
            return super().run(command, cwd, timeout_s, **kwargs)

    runner = _DiffWritingRunner(exit_code=0)
    adapter = CodexCLIAdapter()
    monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)

    result = await adapter.execute(_task(), _ctx(), workspace, Budget())

    assert result.status == RunStatus.SUCCEEDED
    assert result.error is None
    assert result.diff is not None and result.diff.changed_files


@pytest.mark.asyncio
async def test_exit0_no_diff_is_failed(monkeypatch, workspace) -> None:
    monkeypatch.setattr(CodexCLIAdapter, "_requirement_present", lambda self: True)
    runner = _FakeRunner(exit_code=0)
    adapter = CodexCLIAdapter()
    monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)

    result = await adapter.execute(_task(), _ctx(), workspace, Budget())

    assert result.status == RunStatus.FAILED
    assert result.error == "codex produced no diff"


@pytest.mark.asyncio
async def test_invocation_cap_blocks_run(monkeypatch, workspace) -> None:
    """A zero invocation cap blocks execution cleanly (defensive guard)."""
    monkeypatch.setattr(CodexCLIAdapter, "_requirement_present", lambda self: True)
    runner = _FakeRunner(exit_code=0)
    adapter = CodexCLIAdapter(max_invocations=0)
    monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)

    result = await adapter.execute(_task(), _ctx(), workspace, Budget())

    assert result.status == RunStatus.FAILED
    assert result.error == "budget_exceeded:invocations"
    assert runner.calls == []  # runner never invoked


@pytest.mark.asyncio
async def test_trace_built_from_result_is_harness_and_named(monkeypatch, workspace) -> None:
    monkeypatch.setattr(CodexCLIAdapter, "_requirement_present", lambda self: True)
    runner = _FakeRunner(exit_code=1)
    adapter = CodexCLIAdapter()
    monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)

    result = await adapter.execute(_task(), _ctx(), workspace, Budget())
    attempt = AgentAttempt(
        task_id="t", agent_kind=adapter.kind, agent_name=adapter.name,
        model_name=adapter.model_name, started_at=utcnow(),
    )
    trace = build_agent_trace(attempt, result, is_harness=adapter.is_harness, task_id="t")

    assert trace.adapter_name == "codex_cli"
    assert trace.is_harness is True
    # The mediated codex invocation shows up as a command in the trace.
    assert trace.commands == 1


def test_max_invocations_constant() -> None:
    assert codex_mod.MAX_INVOCATIONS == 1
