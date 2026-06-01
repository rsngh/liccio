"""Live OpenAI harness adapter (round-2 Block I).

Skipped unless OPENAI_API_KEY is set. Runs a real tool-loop on the divide bug
and asserts trace capture (tool calls, file writes), diff, tokens, no leak.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from git import Repo

from acp.agents.openai_harness import OpenAIHarnessAdapter
from acp.core.enums import RunStatus
from acp.schemas.agent import Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

pytestmark = pytest.mark.live
LIVE = bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.skipif(not LIVE, reason="no OPENAI_API_KEY")
def test_harness_live_tiny_bugfix(tmp_path) -> None:
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    from acp.core.config import reset_settings

    reset_settings()
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
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                    default_policy())

    adapter = OpenAIHarnessAdapter(max_steps=6)
    assert adapter.is_harness is True
    if not asyncio.run(adapter.healthcheck()).available:
        pytest.skip("openai unavailable")
    task = Task(repo_id=r.id, title="Fix divide by zero",
                body="divide() returns 0 when b==0; make it raise ZeroDivisionError. "
                     "Edit calculator.py.",
                acceptance_criteria=["divide(x,0) raises ZeroDivisionError"])
    pack = ContextPack(repo_id=r.id, task_id=task.id, snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path="calculator.py",
                                          content=(ws.path / "calculator.py").read_text())])
    budget = Budget(max_cost_usd=0.5, max_wall_time_s=120)
    res = asyncio.run(adapter.execute(task, pack, ws, budget))

    assert res.status == RunStatus.SUCCEEDED
    # real harness trace captured
    assert res.tool_calls, "no tool calls captured"
    names = {tc.tool_name for tc in res.tool_calls}
    assert "write_file" in names
    assert res.metadata["files_written"]
    assert res.diff is not None and res.diff.changed_files
    assert res.input_token_count > 0 and res.output_token_count > 0
    assert res.metadata["session_id"]
    # the fix raises on zero division
    assert "raise" in (ws.path / "calculator.py").read_text()
    # no secret leak in captured tool results
    key = os.environ["OPENAI_API_KEY"]
    assert all(key not in (tc.result_summary or "") for tc in res.tool_calls)
