"""Durable cross-process resume (round-1 goal §1, §8)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import HumanVerdict, RunStatus
from acp.schemas.human_review import HumanLabel

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'durable.db'}",
        artifact_dir=tmp_path / "art",
        workspace_dir=tmp_path / "ws",
    )


def _repo(svc: AppService, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    return svc.create_repo("d", str(src), default_branch="master")


def test_run_state_persisted_and_loadable(settings, tmp_path) -> None:
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide", "zero",
                           metadata={"files": {"calculator.py": FIXED}})
    state = svc.run_task(task.id)

    # A brand-new service (new process) can load the run from the DB.
    fresh = AppService(settings)
    loaded = fresh.get_run(state.run_id)
    assert loaded is not None
    assert loaded.run_id == state.run_id


def test_human_review_resume_across_process(settings, tmp_path) -> None:
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    # high-risk task -> pauses for human review
    task = svc.create_task(repo.id, "Update auth password hashing",
                           "change login auth", metadata={"files": {"calculator.py": FIXED}})
    state = svc.run_task(task.id)
    assert state.status == RunStatus.WAITING_FOR_HUMAN.value or \
        state.status == RunStatus.WAITING_FOR_HUMAN

    # New process: rehydrate runner from DB and resume with a human label.
    fresh = AppService(settings)
    loaded = fresh.get_run(state.run_id)
    assert loaded is not None
    label = HumanLabel(review_item_id=loaded.human_review_item_id or "x", task_id=task.id,
                       verdict=HumanVerdict.PASS, score=0.9, reason="ok")
    resumed = fresh.resume_run(state.run_id, label)
    assert resumed.status in (RunStatus.SUCCEEDED, RunStatus.SUCCEEDED.value)
    assert resumed.reward_event_id
