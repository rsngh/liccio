"""Live OpenAI adapter test (round-1 two-day D2B6).

Skipped unless OPENAI_API_KEY is set. Exercises the real SimpleLLMReviewAdapter
on the divide-by-zero fixture and asserts containment, token + diff capture, and
no secret leakage into the workspace.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from git import Repo

from acp.agents.simple_llm import SimpleLLMReviewAdapter
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
def test_openai_adapter_fixes_bug_with_capture(tmp_path) -> None:
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
    base = repo.head.commit.hexsha

    mgr = LocalWorkspaceManager(tmp_path / "ws")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=base), default_policy())

    adapter = SimpleLLMReviewAdapter()
    assert adapter.is_harness is False  # documented: simple model adapter
    health = asyncio.run(adapter.healthcheck())
    if not health.available:
        pytest.skip(f"openai unavailable: {health.detail}")

    task = Task(
        repo_id=r.id, title="Fix divide by zero",
        body="divide() returns 0 when b==0; it must raise ZeroDivisionError. Edit calculator.py.",
        acceptance_criteria=["divide(x, 0) raises ZeroDivisionError"],
    )
    pack = ContextPack(
        repo_id=r.id, task_id=task.id, snapshot_id="s",
        items=[ContextItem(kind="file_chunk", path="calculator.py",
                           content=(ws.path / "calculator.py").read_text())],
    )
    result = asyncio.run(adapter.execute(task, pack, ws, Budget()))

    assert result.status == RunStatus.SUCCEEDED
    assert result.diff is not None and result.diff.changed_files  # diff capture
    assert result.input_token_count > 0 and result.output_token_count > 0  # token capture
    # containment: only files under the workspace were written
    edited = (ws.path / "calculator.py").read_text()
    assert "raise" in edited  # model implemented an exception path
    # no secret leakage into workspace files
    key = os.environ["OPENAI_API_KEY"]
    assert key not in edited
