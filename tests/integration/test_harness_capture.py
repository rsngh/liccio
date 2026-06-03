"""Harness tool-capture tests without an LLM (round-2 Block I)."""

from __future__ import annotations

import sys

import pytest
from git import Repo

from acp.agents.openai_harness import HarnessTools, OpenAIHarnessAdapter
from acp.schemas.repo import Repository, RepoSnapshot
from acp.workspaces.command_runner import CommandRunner
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
    return mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                      default_policy())


def test_tools_capture_read_write_command(workspace) -> None:
    runner = CommandRunner(allowed_root=workspace.path, scrub_secrets=True)
    tools = HarnessTools(workspace=workspace, runner=runner)
    assert "divide" in tools.read_file("calculator.py")
    assert tools.write_file("calculator.py", "def divide(a, b):\n    return a / b\n") == "ok"
    out = tools.run_command([sys.executable, "-c", "print('hello')"])
    assert "hello" in out
    # capture
    names = [tc.tool_name for tc in tools.tool_calls]
    assert names == ["read_file", "write_file", "run_command"]
    assert tools.files_written == ["calculator.py"]
    assert len(tools.command_runs) == 1


def test_tools_write_outside_workspace_blocked(workspace) -> None:
    runner = CommandRunner(allowed_root=workspace.path)
    tools = HarnessTools(workspace=workspace, runner=runner)
    res = tools.write_file("../escape.py", "x = 1")
    assert res.startswith("ERROR")
    assert tools.tool_calls[-1].error  # recorded as a failed tool call


def test_harness_is_marked_real() -> None:
    assert OpenAIHarnessAdapter().is_harness is True


def test_finalize_classifies_provider_timeout_as_timed_out(workspace) -> None:
    # An SDK timeout string ("Request timed out.") must map to TIMED_OUT, not a
    # capability FAILED -- else infra latency poisons the capability matrix.
    import time

    from acp.agents.harness_base import finalize_result, make_tools
    from acp.core.enums import RunStatus

    tools = make_tools(workspace)
    res = finalize_result(tools=tools, workspace=workspace, t0=time.monotonic(),
                          model="gpt-4o-mini", in_tok=10, out_tok=5,
                          error="Request timed out.", session_id="s1")
    assert res.status == RunStatus.TIMED_OUT
