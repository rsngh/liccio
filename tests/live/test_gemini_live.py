"""Live GeminiAgentAdapter against the real Google Gemini API.

Skipped unless GEMINI_API_KEY is set. Proves the third provider family (Google
Gemini, distinct from the Anthropic tiers and OpenAI) actually solves a tiny
no-patch bugfix end to end, so the heterogeneity claim spans a real cross-vendor
model — not just Anthropic sizes. Mirrors ``test_claude_harness_live.py``.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from git import Repo

from acp.agents.gemini_agent import GeminiAgentAdapter
from acp.core.config import reset_settings
from acp.schemas.agent import Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

pytestmark = [pytest.mark.live, pytest.mark.live_gemini]

LIVE = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("ACP_GEMINI_API_KEY"))


@pytest.mark.skipif(not LIVE, reason="no GEMINI_API_KEY")
def test_gemini_solves_no_patch_bugfix(tmp_path) -> None:
    reset_settings()
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
    ws = mgr.create(
        r,
        RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
        default_policy(),
    )

    adapter = GeminiAgentAdapter(model="gemini-2.5-flash", thinking_budget=0)
    task = Task(
        repo_id=r.id,
        title="Fix divide-by-zero",
        body="divide() returns 0 when the divisor is 0; it must raise ZeroDivisionError.",
        acceptance_criteria=["divide(x, 0) raises ZeroDivisionError"],
    )
    pack = ContextPack(
        task_id="t",
        repo_id=r.id,
        snapshot_id="s",
        instructions=(
            "Fix calculator.py so that divide(a, b) raises ZeroDivisionError when b == 0 "
            "and otherwise returns a / b."
        ),
        items=[
            ContextItem(
                kind="file_chunk",
                path="calculator.py",
                content="def divide(a, b):\n    return 0\n",
            )
        ],
    )
    result = asyncio.run(
        adapter.execute(task, pack, ws, Budget(max_cost_usd=0.5, max_wall_time_s=120))
    )
    assert result.status == "succeeded", result.error
    assert "calculator.py" in result.diff.changed_files
    assert result.input_token_count > 0
    # the real fix raises on a zero divisor (the adapter writes into the workspace,
    # so assert on the captured diff rather than the untouched source tree)
    assert "ZeroDivisionError" in result.diff.unified_diff or "raise" in result.diff.unified_diff
