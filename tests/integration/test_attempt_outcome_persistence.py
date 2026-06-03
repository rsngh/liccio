"""Durable attempt-outcome persistence (Alpha 11/12 WS8)."""

from __future__ import annotations

import acp.db.models  # noqa: F401 - register all ORM tables before create_all
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.evaluation.measurement_hygiene import hygiene_from_store, ingest_attempt_outcomes


def _sessions(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'p.db'}")
    create_all(engine)
    return make_session_factory(engine)


def test_ingest_and_read_back_preserves_outcomes(tmp_path) -> None:
    cells = [
        {"adapter": "openai_harness", "task_type": "bugfix", "success": True,
         "status": "succeeded", "tool_calls": 2, "is_harness": True},
        {"adapter": "openai_harness", "task_type": "bugfix", "success": False,
         "status": "timed_out", "timed_out": True, "tool_calls": 0,
         "error": "timed out", "is_harness": True},  # infra -> inconclusive
        {"adapter": "openai_harness", "task_type": "bugfix", "success": False,
         "status": "failed", "tool_calls": 3, "is_harness": True},  # task_failure
    ]
    sf = _sessions(tmp_path)
    with session_scope(sf) as s:
        assert ingest_attempt_outcomes(s, cells) == 3
    with session_scope(sf) as s:
        rep = hygiene_from_store(s, adapter_name="openai_harness")
    # The infra timeout stays inconclusive; solve-rate is 1/2 over conclusive rows.
    assert rep.n_conclusive == 2 and rep.n_infra == 1
    assert rep.solve_rate == 0.5
