"""Live vendor-harness smoke (Alpha 8, WS9).

Gated behind ACP_LIVE_CODEX *and* the codex binary being present, so it is
skipped by default (codex behavior varies and may need auth/network). When
enabled it runs the real `codex_cli` vendor harness on a tiny no-patch bugfix and
asserts a normalized, secret-free `AgentTrace` — and that execute() never raises.
"""

from __future__ import annotations

import asyncio
import os
import shutil

import pytest
from git import Repo

from acp.agents.codex_cli import CodexCLIAdapter
from acp.agents.trace import build_agent_trace
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

pytestmark = [pytest.mark.live, pytest.mark.live_codex]
LIVE = bool(os.environ.get("ACP_LIVE_CODEX")) and shutil.which("codex") is not None


@pytest.mark.skipif(not LIVE, reason="ACP_LIVE_CODEX unset or codex binary missing")
def test_codex_cli_live_smoke(tmp_path) -> None:
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text(
        "def divide(a, b):\n    if b == 0:\n        return 0  # bug\n    return a / b\n"
    )
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    ws = LocalWorkspaceManager(tmp_path / "ws").create(
        r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
        default_policy())

    adapter = CodexCLIAdapter()
    task = Task(repo_id=r.id, title="Fix divide by zero",
                body="divide() returns 0 when b==0; make it raise ZeroDivisionError.",
                acceptance_criteria=["divide(x,0) raises"])
    pack = ContextPack(repo_id=r.id, task_id=task.id, snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path="calculator.py",
                                          content=(ws.path / "calculator.py").read_text())])
    # Defensive: execute must never raise, even if codex misbehaves.
    result = asyncio.run(adapter.execute(task, pack, ws, Budget(max_cost_usd=0.5,
                                                                max_wall_time_s=60)))
    attempt = AgentAttempt(task_id=task.id, agent_kind=adapter.kind,
                           agent_name=adapter.name)
    trace = build_agent_trace(attempt, result, is_harness=True, task_id=task.id)
    assert trace.adapter_name == "codex_cli"
    assert trace.is_harness is True
    # No secret leakage in any recorded tool output.
    for env_key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(env_key)
        if secret:
            assert all(secret not in (tc.result_summary or "")
                       for tc in (result.tool_calls or []))
