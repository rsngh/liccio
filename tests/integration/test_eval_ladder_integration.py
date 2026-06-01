"""Eval ladder wired into the live loop (round-1 goal §7)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.db.repositories import EntityStore
from acp.db.session import session_scope
from acp.schemas.evaluation import WeakLabel

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'e.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "e"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("e", str(src), default_branch="master")


def test_weak_label_and_judges_and_al_in_loop(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    task = service.create_task(repo.id, "Fix divide bug", "zero divisor",
                              metadata={"files": {"calculator.py": FIXED}})
    service.run_task(task.id)
    runner = service._runners[list(service._runs)[0]]

    # eval ladder ran in the loop
    assert runner.artifacts.weak_label is not None
    assert len(runner.artifacts.judge_results) == 5
    assert runner.artifacts.al_score is not None

    # weak label persisted to DB
    with session_scope(service.sessions) as session:
        labels = EntityStore(session).list_by(WeakLabel, task_id=task.id)
    assert labels
