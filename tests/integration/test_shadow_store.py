"""Shadow-decision store + human-feedback -> training data (Alpha 27)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.db.repositories import EntityStore
from acp.db.session import make_engine, make_session_factory, session_scope
from acp.orchestration.shadow_store import (
    feedback_to_training,
    inbox_summary,
    record_human_feedback,
    save_decision,
)
from acp.schemas.shadow_decision import ShadowDecisionRecord


def _sf(tmp_path):
    from acp.db.session import create_all
    e = make_engine(f"sqlite:///{tmp_path / 'sd.db'}")
    create_all(e)
    return make_session_factory(e)


def _rec(task_id="t1", **kw):
    return ShadowDecisionRecord(task_id=task_id, task_type="bugfix", risk="low",
                                recommended_adapter="openai_harness", **kw)


def test_persist_and_query(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        save_decision(EntityStore(s), _rec())
    with session_scope(sf) as s:
        rows = EntityStore(s).list_by(ShadowDecisionRecord, task_id="t1")
        assert len(rows) == 1 and rows[0].autonomous_write is False


def test_human_feedback_becomes_training(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        a = save_decision(EntityStore(s), _rec("accept_task"))
        o = save_decision(EntityStore(s), _rec("override_task"))
    with session_scope(sf) as s:
        st = EntityStore(s)
        record_human_feedback(st, a.id, verdict="accepted", observed_outcome="solved")
        record_human_feedback(st, o.id, verdict="overridden", human_choice="claude_harness")
    with session_scope(sf) as s:
        rows = EntityStore(s).list_by(ShadowDecisionRecord)
        examples = feedback_to_training(rows)
        assert len(examples) == 2
        acc = next(e for e in examples if e["polarity"] == "positive")
        corr = next(e for e in examples if e["polarity"] == "corrective")
        assert acc["target"] == "openai_harness"          # accepted -> recommendation
        assert corr["target"] == "claude_harness"          # overridden -> human's choice


def test_inbox_summary_and_zero_write_audit(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        st = EntityStore(s)
        for i in range(3):
            d = save_decision(st, _rec(f"t{i}"))
            if i == 0:
                record_human_feedback(st, d.id, verdict="accepted")
    with session_scope(sf) as s:
        rows = EntityStore(s).list_by(ShadowDecisionRecord)
        summ = inbox_summary(rows)
        assert summ["n_decisions"] == 3 and summ["by_verdict"]["pending"] == 2
        assert summ["acceptance_rate"] == 1.0 and summ["no_autonomous_writes"]


def test_feedback_on_missing_decision_is_safe(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        assert record_human_feedback(EntityStore(s), "nope", verdict="accepted") is None
