"""Durable drift/demotion persistence (Alpha 11, WS8)."""

from __future__ import annotations

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.learning.drift import WindowedOutcome


def _svc(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'd.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


class _Ens:
    learned_promoted = True


def test_drift_demotion_is_persisted_and_inspectable(tmp_path) -> None:
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.schemas.drift import (
        DriftReportEntity,
        ModelDemotionEventEntity,
        ModelPromotionState,
    )

    svc = _svc(tmp_path)
    baseline = [WindowedOutcome(0.9 if i % 2 == 0 else 0.1, i % 2 == 0, "low", i)
                for i in range(40)]
    recent = [WindowedOutcome(0.9, False, "high", 100 + i) for i in range(20)]
    ens = _Ens()

    result = svc.run_and_persist_drift(ens, model_name="learned_viability",
                                       baseline=baseline, recent=recent)
    assert result["demoted"] is True
    assert result["persisted"] is True
    assert ens.learned_promoted is False

    # Durable + inspectable: the report, demotion event, and promotion state exist.
    with session_scope(svc.sessions) as s:
        es = EntityStore(s)
        reports = es.list_by(DriftReportEntity, model_name="learned_viability")
        events = es.list_by(ModelDemotionEventEntity, model_name="learned_viability")
        states = es.list_by(ModelPromotionState, model_name="learned_viability")
    assert reports and reports[0].demote_recommended is True
    assert events and events[0].drift_report_id == reports[0].id
    assert states and states[0].promoted is False and states[0].last_event == "demoted"


def test_stable_model_not_demoted_or_persisted_as_event(tmp_path) -> None:
    from acp.db.repositories import EntityStore
    from acp.db.session import session_scope
    from acp.schemas.drift import ModelDemotionEventEntity

    svc = _svc(tmp_path)
    stable = [WindowedOutcome(0.9 if i % 2 == 0 else 0.1, i % 2 == 0, "low", i)
              for i in range(40)]
    ens = _Ens()
    result = svc.run_and_persist_drift(ens, model_name="m", baseline=stable,
                                       recent=stable[:20])
    assert result["demoted"] is False
    with session_scope(svc.sessions) as s:
        events = EntityStore(s).list_by(ModelDemotionEventEntity, model_name="m")
    assert events == []
