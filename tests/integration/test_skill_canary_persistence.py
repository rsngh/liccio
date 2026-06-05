"""Staged-canary persistence survives process restart (Alpha 22 WS13)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.skill_canary_run import SkillCanaryRun, SkillCanaryStageRecord


def _stage(stage, decision="advance", **kw):
    return SkillCanaryStageRecord(stage=stage, canary_n=10, canary_successes=9,
                                  decision=decision, **kw)


def test_canary_run_survives_restart(tmp_path) -> None:
    db = tmp_path / "canary.db"
    # "Process 1": create + persist a canary mid-rollout.
    eng = make_engine(f"sqlite:///{db}")
    create_all(eng)
    sf = make_session_factory(eng)
    run = SkillCanaryRun(scope_key="bugfix|*", candidate_skill_id="skill_new",
                         baseline_skill_id="skill_old", current_stage=0.25,
                         stages=[_stage(0.05), _stage(0.25)])
    with session_scope(sf) as s:
        EntityStore(s).save(run, extra_index={"scope_key": run.scope_key,
                                              "status": run.status})
    # "Process 2": fresh engine on the same DB reads the run back intact.
    eng2 = make_engine(f"sqlite:///{db}")
    sf2 = make_session_factory(eng2)
    with session_scope(sf2) as s:
        runs = EntityStore(s).list_by(SkillCanaryRun, scope_key="bugfix|*")
    assert len(runs) == 1
    r = runs[0]
    assert r.current_stage == 0.25 and len(r.stages) == 2
    assert r.candidate_skill_id == "skill_new" and r.baseline_skill_id == "skill_old"
    assert r.stages[1].stage == 0.25 and r.stages[1].canary_successes == 9


def test_query_by_status(tmp_path) -> None:
    eng = make_engine(f"sqlite:///{tmp_path / 'q.db'}")
    create_all(eng)
    sf = make_session_factory(eng)
    with session_scope(sf) as s:
        es = EntityStore(s)
        for st in ("running", "promoted", "rolled_back"):
            run = SkillCanaryRun(scope_key="x", candidate_skill_id="c", status=st)
            es.save(run, extra_index={"scope_key": "x", "status": st})
    with session_scope(sf) as s:
        promoted = EntityStore(s).list_by(SkillCanaryRun, status="promoted")
    assert len(promoted) == 1 and promoted[0].status == "promoted"
