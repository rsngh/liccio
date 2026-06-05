"""Canary -> deploy/rollback integration (Alpha 22 WS15)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.skill import SkillDocument, SkillScope
from acp.schemas.skill_canary_run import SkillCanaryRun
from acp.training.skill_canary_platform import (
    StageMetrics,
    staged_canary_deploy,
)
from acp.training.skill_registry import active_skill_for


def _sf(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'sc.db'}")
    create_all(e)
    return make_session_factory(e)


def _good():
    return StageMetrics(control_solve=0.6, canary_solve=0.95, control_cost=0.01,
                        canary_cost=0.011, measurement_quality=1.0, control_har=1.0,
                        canary_har=1.0, control_hfr=0.9, canary_hfr=0.95)


def _candidate():
    return SkillDocument(name="bugfix", content="# s\n- run the tests before finishing\n",
                         version=2, status=SkillStatus.CANDIDATE,
                         scope=SkillScope(task_type="bugfix"))


def test_clean_rollout_promotes_and_deploys(tmp_path) -> None:
    sf = _sf(tmp_path)
    metrics = {s: _good() for s in (0.05, 0.25, 0.50, 1.0)}
    with session_scope(sf) as s:
        run, dep = staged_canary_deploy(EntityStore(s), _candidate(), "skill_old", metrics)
    assert run.status == "promoted" and dep.deployed
    with session_scope(sf) as s:
        assert active_skill_for(EntityStore(s), task_type="bugfix") is not None
        persisted = EntityStore(s).list_by(SkillCanaryRun, status="promoted")
        assert len(persisted) == 1 and persisted[0].current_stage == 1.0


def test_regression_rolls_back_and_leaves_advisory(tmp_path) -> None:
    sf = _sf(tmp_path)
    bad = _good()
    bad.canary_solve = 0.3  # regresses below control at 50%
    metrics = {0.05: _good(), 0.25: _good(), 0.50: bad, 1.0: _good()}
    with session_scope(sf) as s:
        run, dep = staged_canary_deploy(EntityStore(s), _candidate(), None, metrics)
    assert run.status == "rolled_back" and not dep.deployed
    assert run.current_stage == 0.50
    with session_scope(sf) as s:
        # No active skill deployed; candidate left advisory.
        assert active_skill_for(EntityStore(s), task_type="bugfix") is None
        assert EntityStore(s).list_by(SkillCanaryRun, status="rolled_back")
