"""Real crash-resume harness (round-1 two-day D1B3 / §B)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import HumanVerdict, RunStatus
from acp.orchestration.runner import WorkflowRunner
from acp.schemas.human_review import HumanLabel

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"
RESUMABLE_NODES = [
    "classify_task", "compile_context", "route_task",
    "launch_agent_attempts", "run_verification", "evaluate_attempt", "score_signals",
]


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


@pytest.mark.parametrize("crash_node", RESUMABLE_NODES)
def test_crash_after_node_then_resume(tmp_path, crash_node) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": FIXED}})

    # Run with an injected stop right after `crash_node`, persisting via the
    # service, then discard the runner (simulating process death).
    runner = WorkflowRunner(
        repo, svc.registry, Path(settings.workspace_dir),
        artifact_store=svc.artifact_store, on_persist=svc._persist_run,
        policy=svc.policy, stop_after_node=crash_node,
    )
    state = asyncio.run(runner.run(task))
    assert crash_node in state.completed_nodes
    assert state.status not in (RunStatus.SUCCEEDED, RunStatus.SUCCEEDED.value)
    del runner

    # Brand-new service (new process) loads + resumes from the DB.
    fresh = AppService(settings)
    resumed = fresh.resume_run(state.run_id)
    assert resumed.status in (RunStatus.SUCCEEDED, RunStatus.SUCCEEDED.value)
    assert resumed.reward_event_id

    # No duplicate finalization / reward.
    assert resumed.completed_nodes.count("finalize_run") == 1
    graph = fresh.full_run_graph(state.run_id)
    assert len(graph["reward_events"]) == 1


def test_crash_while_waiting_for_human_then_resume(tmp_path) -> None:
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Update auth password hashing", "change login auth",
                          metadata={"files": {"calculator.py": FIXED}})
    state = svc.run_task(task.id)
    assert state.status in (RunStatus.WAITING_FOR_HUMAN, RunStatus.WAITING_FOR_HUMAN.value)

    # New process: list reviews, label, resume to completion.
    fresh = AppService(settings)
    reviews = fresh.list_reviews()
    assert reviews
    label = HumanLabel(review_item_id=state.human_review_item_id, task_id=task.id,
                       verdict=HumanVerdict.PASS, score=0.9, reason="ok")
    resumed = fresh.resume_run(state.run_id, label)
    assert resumed.status in (RunStatus.SUCCEEDED, RunStatus.SUCCEEDED.value)
    assert resumed.completed_nodes.count("finalize_run") == 1
