"""Exhaustive crash-resume across every node (round-2 Block C)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import HumanVerdict, RunStatus
from acp.orchestration.runner import NODE_ORDER, WorkflowRunner
from acp.schemas.human_review import HumanLabel

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"
# every node except the terminal finalize is a crash point worth resuming from
CRASH_NODES = [n for n in NODE_ORDER if n != "finalize_run"]


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'c.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    )


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "c"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("c", str(src), default_branch="master")


def _assert_clean_finish(fresh: AppService, run_id: str, resumed) -> None:
    assert resumed.status in (RunStatus.SUCCEEDED, RunStatus.SUCCEEDED.value)
    assert resumed.completed_nodes.count("finalize_run") == 1
    graph = fresh.full_run_graph(run_id)
    assert len(graph["reward_events"]) == 1
    # no duplicate evaluation / attempt explosion
    assert graph["evaluation"] is not None


@pytest.mark.parametrize("crash_node", CRASH_NODES)
def test_crash_after_every_node_then_resume(tmp_path, crash_node) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": FIXED}})
    runner = WorkflowRunner(
        repo, svc.registry, Path(settings.workspace_dir),
        artifact_store=svc.artifact_store, on_persist=svc._persist_run,
        policy=svc.policy, stop_after_node=crash_node,
    )
    state = asyncio.run(runner.run(task))
    assert crash_node in state.completed_nodes
    del runner
    fresh = AppService(settings)
    resumed = fresh.resume_run(state.run_id)
    _assert_clean_finish(fresh, state.run_id, resumed)


@pytest.mark.parametrize("crash_node", CRASH_NODES)
def test_exception_after_every_node_no_corruption(tmp_path, crash_node) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": FIXED}})
    runner = WorkflowRunner(
        repo, svc.registry, Path(settings.workspace_dir),
        artifact_store=svc.artifact_store, on_persist=svc._persist_run,
        policy=svc.policy, fail_after_node=crash_node,
    )
    state = asyncio.run(runner.run(task))
    assert state.status in (RunStatus.FAILED, RunStatus.FAILED.value)
    del runner
    fresh = AppService(settings)
    resumed = fresh.resume_run(state.run_id)
    _assert_clean_finish(fresh, state.run_id, resumed)


@pytest.mark.parametrize("crash_node", CRASH_NODES)
def test_crash_before_every_node_then_resume(tmp_path, crash_node) -> None:
    """Pre-persist crash: die before a node runs, so it never completes. Resume
    must re-enter that node and finish cleanly (per-node re-execution idempotency)."""
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": FIXED}})
    runner = WorkflowRunner(
        repo, svc.registry, Path(settings.workspace_dir),
        artifact_store=svc.artifact_store, on_persist=svc._persist_run,
        policy=svc.policy, fail_before_node=crash_node,
    )
    state = asyncio.run(runner.run(task))
    assert state.status in (RunStatus.FAILED, RunStatus.FAILED.value)
    # The crashing node never made it into completed_nodes.
    assert crash_node not in state.completed_nodes
    del runner
    fresh = AppService(settings)
    resumed = fresh.resume_run(state.run_id)
    _assert_clean_finish(fresh, state.run_id, resumed)
    # The node that crashed pre-persist is present exactly once after resume.
    assert resumed.completed_nodes.count(crash_node) == 1


def test_waiting_for_human_no_label_does_not_finalize(tmp_path) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Update auth password hashing", "auth",
                          metadata={"files": {"calculator.py": FIXED}})
    state = svc.run_task(task.id)
    assert state.status in (RunStatus.WAITING_FOR_HUMAN, RunStatus.WAITING_FOR_HUMAN.value)
    # no label -> no finalize, no reward yet
    graph = svc.full_run_graph(state.run_id)
    assert "finalize_run" not in state.completed_nodes
    assert graph["reward_events"] == []


def test_human_label_after_restart_finalizes_once(tmp_path) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Update auth password hashing", "auth",
                          metadata={"files": {"calculator.py": FIXED}})
    state = svc.run_task(task.id)
    fresh = AppService(settings)
    label = HumanLabel(review_item_id=state.human_review_item_id, task_id=task.id,
                       verdict=HumanVerdict.PASS, score=0.9, reason="ok")
    resumed = fresh.resume_run(state.run_id, label)
    _assert_clean_finish(fresh, state.run_id, resumed)
