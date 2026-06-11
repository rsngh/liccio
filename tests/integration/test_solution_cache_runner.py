# ruff: noqa: E501
"""Production solution-memory: a verified cached diff solves a recurrence with ZERO agent calls.

Drives the real WorkflowRunner with an opt-in DiffCache pre-populated with the fix diff. On a hit the
runner applies it as a synthetic attempt that flows through the normal verification nodes — the run
succeeds, the only attempt is `solution_cache`, and the live PatchAgent never executes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from git import Repo

from acp.agents.patch_agent import PatchAgentAdapter
from acp.agents.registry import AgentRegistry
from acp.core.enums import RunStatus
from acp.memory.diff_cache import DiffCache
from acp.orchestration.runner import WorkflowRunner
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
    cw = repo.config_writer()
    cw.set_value("user", "name", "t")
    cw.set_value("user", "email", "t@e.com")
    cw.set_value("commit", "gpgsign", "false")
    cw.release()
    repo.index.add(["pyproject.toml", "src/calculator.py", "tests/test_calculator.py", "AGENTS.md"])
    repo.index.commit("init")
    return Repository(name="buggy", local_path=str(dst), default_branch="master")


def _fix_diff(repo_path: Path) -> str:
    """The verified unified diff (buggy calculator.py -> FIXED_CALC), via git diff then revert."""
    (repo_path / "src/calculator.py").write_text(FIXED_CALC)
    diff = subprocess.run(["git", "-C", str(repo_path), "diff"], capture_output=True, text=True, check=True).stdout
    subprocess.run(["git", "-C", str(repo_path), "checkout", "--", "src/calculator.py"], check=True)
    return diff


async def test_cached_diff_solves_recurrence_with_zero_agent_calls(tmp_path) -> None:
    repo = _make_repo(tmp_path)
    cache = DiffCache()
    cache.record(repo_id=repo.id, failure_signature="ZeroDivisionError:divide",
                 unified_diff=_fix_diff(Path(repo.local_path)), verified=True)
    reg = AgentRegistry()
    reg.register(PatchAgentAdapter())
    runner = WorkflowRunner(repo, reg, tmp_path / "ws", solution_cache=cache)
    task = Task(repo_id=repo.id, title="Fix divide by zero",
                body="divide() returns 0 on zero divisor; must raise ZeroDivisionError",
                acceptance_criteria=["divide(x,0) raises ZeroDivisionError"],
                metadata={"failure_signature": "ZeroDivisionError:divide"})
    state = await runner.run(task)

    assert state.status == RunStatus.SUCCEEDED
    assert state.scratch.get("solution_cache_hit") is True
    names = [a.agent_name for a in runner.artifacts.attempts]
    assert names == ["solution_cache"]          # the live PatchAgent never ran
    assert any(e.event_type == "solution_cache_hit" for e in runner.artifacts.audit_events)


async def test_cache_miss_falls_through_to_live_agent(tmp_path) -> None:
    # no matching signature -> cache never fires -> the live PatchAgent solves it normally
    repo = _make_repo(tmp_path)
    cache = DiffCache()
    cache.record(repo_id=repo.id, failure_signature="OTHER",
                 unified_diff=_fix_diff(Path(repo.local_path)), verified=True)
    reg = AgentRegistry()
    reg.register(PatchAgentAdapter())
    runner = WorkflowRunner(repo, reg, tmp_path / "ws", solution_cache=cache)
    task = Task(repo_id=repo.id, title="Fix divide by zero", body="must raise ZeroDivisionError",
                metadata={"failure_signature": "ZeroDivisionError:divide",
                          "files": {"src/calculator.py": FIXED_CALC}})
    state = await runner.run(task)
    assert state.status == RunStatus.SUCCEEDED
    assert state.scratch.get("solution_cache_hit") is None
    assert "solution_cache" not in [a.agent_name for a in runner.artifacts.attempts]
