"""DB migration + persistence round-trip tests (charter §8.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from acp import schemas as s
from acp.db.models import ALL_MODELS
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "src/acp/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url.replace("+aiosqlite", ""))
    return cfg


def test_alembic_upgrade_head_creates_all_tables(tmp_path, monkeypatch) -> None:
    db_file = tmp_path / "acp.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("ACP_DATABASE_URL", db_url)
    from acp.core.config import reset_settings

    reset_settings()
    command.upgrade(_alembic_config(db_url), "head")

    engine = make_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    for model in ALL_MODELS:
        assert model.__tablename__ in tables


@pytest.fixture
def store(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'g.db'}")
    create_all(engine)
    return make_session_factory(engine)


def test_full_workflow_graph_insert_and_queries(store) -> None:
    trace_id = "trace_abc"
    task = s.Task(repo_id="repo_1", title="fix bug")
    attempt = s.AgentAttempt(
        task_id=task.id, agent_kind="fake", agent_name="fake", trace_id=trace_id
    )
    cmd = s.CommandRunRecord(
        attempt_id=attempt.id, argv=["pytest"], cwd="/ws", trace_id=trace_id
    )
    evidence = s.Evidence(
        task_id=task.id, attempt_id=attempt.id, kind="unit_test", name="pytest", status="pass"
    )
    reward = s.RewardEvent(task_id=task.id, attempt_id=attempt.id, reward=2.5,
                           components={"task_success": 1.0})

    with session_scope(store) as session:
        es = EntityStore(session)
        es.save(s.Repository(id="repo_1", name="demo"))
        es.save(task)
        es.save(attempt)
        es.save(cmd)
        es.save(evidence)
        es.save(reward)

    with session_scope(store) as session:
        es = EntityStore(session)
        # round-trip
        got = es.get(s.Task, task.id)
        assert got is not None and got.title == "fix bug"
        # query by task_id returns all children
        by_task = es.all_for_task(task.id)
        assert "AgentAttempt" in by_task
        assert "Evidence" in by_task
        assert "RewardEvent" in by_task
        # query by trace_id
        by_trace = es.all_for_trace(trace_id)
        assert "AgentAttempt" in by_trace
        assert "CommandRunRecord" in by_trace


def test_json_metadata_survives_roundtrip(store) -> None:
    task = s.Task(repo_id="r", title="t", metadata={"nested": {"a": [1, 2, 3]}, "flag": True})
    with session_scope(store) as session:
        EntityStore(session).save(task)
    with session_scope(store) as session:
        got = EntityStore(session).get(s.Task, task.id)
    assert got is not None
    assert got.metadata == {"nested": {"a": [1, 2, 3]}, "flag": True}


def test_indexed_columns_populated(store) -> None:
    pack = s.ContextPack(repo_id="r", task_id="t", snapshot_id="sn")
    with session_scope(store) as session:
        EntityStore(session).save(pack)
    # content_hash is a computed field -> should be persisted in its column
    from acp.db import models as m

    with session_scope(store) as session:
        row = session.get(m.ContextPack, pack.id)
        assert row is not None
        assert row.content_hash == pack.content_hash
        assert row.task_id == "t"
