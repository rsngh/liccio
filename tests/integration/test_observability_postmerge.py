"""Observability spans + post-merge outcome loop (round-1 goal §8, §9)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.db.repositories import EntityStore
from acp.db.session import session_scope
from acp.schemas.learning import PostMergeOutcome, RewardEvent
from acp.schemas.trace import SpanRecord

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'o.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def _run(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "o"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    repo = svc.create_repo("o", str(src), default_branch="master")
    task = svc.create_task(repo.id, "Fix divide bug", "zero divisor",
                          metadata={"files": {"calculator.py": FIXED}})
    return svc.run_task(task.id), task


def test_node_spans_persisted(service, tmp_path) -> None:
    state, _task = _run(service, tmp_path)
    with session_scope(service.sessions) as s:
        spans = EntityStore(s).list_by(SpanRecord, trace_id=state.trace_id)
    names = {sp.name for sp in spans}
    assert "acp.route_task" in names
    assert "acp.run_verification" in names
    assert all(sp.trace_id == state.trace_id for sp in spans)


def test_post_merge_revert_matures_reward_down(service, tmp_path) -> None:
    state, task = _run(service, tmp_path)
    # baseline reward
    with session_scope(service.sessions) as s:
        before = EntityStore(s).list_by(RewardEvent, task_id=task.id)
    base_reward = before[-1].reward

    service.ingest_outcome(task.id, state.selected_attempt_id, reverted=True)

    with session_scope(service.sessions) as s:
        outcomes = EntityStore(s).list_by(PostMergeOutcome, task_id=task.id)
        rewards = EntityStore(s).list_by(RewardEvent, task_id=task.id)
    assert outcomes and outcomes[0].reverted
    matured = [r for r in rewards if r.label_source == "post_merge"]
    assert matured
    assert matured[-1].reward < base_reward
