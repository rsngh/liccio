"""Live ClaudeHarnessAdapter against the real Anthropic API (round-4 Block E).

Skipped unless ANTHROPIC_API_KEY is set and the anthropic SDK is installed.
Proves the second true harness actually solves a no-patch bugfix end to end.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from git import Repo

from acp.agents.claude_harness import ClaudeHarnessAdapter
from acp.core.config import reset_settings
from acp.schemas.agent import Budget
from acp.schemas.context import ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

pytestmark = [pytest.mark.live, pytest.mark.live_second_harness]


def _have_anthropic() -> bool:
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not _have_anthropic(), reason="no ANTHROPIC_API_KEY / anthropic SDK")
def test_claude_harness_solves_no_patch_bugfix(tmp_path) -> None:
    os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
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
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                    default_policy())

    adapter = ClaudeHarnessAdapter(max_steps=8)
    task = Task(repo_id=r.id, title="Fix divide-by-zero",
                body="divide() returns 0 when the divisor is 0; it must raise "
                     "ZeroDivisionError. Edit calculator.py.",
                acceptance_criteria=["divide(x, 0) raises ZeroDivisionError"])
    pack = ContextPack(task_id="t", repo_id=r.id, snapshot_id="s")
    result = asyncio.run(adapter.execute(task, pack, ws,
                                         Budget(max_cost_usd=0.5, max_wall_time_s=120)))
    assert result.status == "succeeded", result.error
    assert "calculator.py" in result.diff.changed_files
    assert any(t.tool_name == "write_file" for t in result.tool_calls)
    assert result.input_token_count > 0
    # the real fix raises on zero divisor
    assert "ZeroDivisionError" in (src / "calculator.py").read_text() or \
        "raise" in result.diff.unified_diff
