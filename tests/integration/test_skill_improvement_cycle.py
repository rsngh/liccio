"""Autonomous skill-improvement cycle + dashboard (Round 18)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_edit import SkillEdit
from acp.training.skill_improvement import (
    SkillScopeJob,
    run_skill_improvement_cycle,
    skill_dashboard,
)
from acp.training.skillopt_backend import ACPInternalSkillOptBackend


def _sf(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'cyc.db'}")
    create_all(e)
    return make_session_factory(e)


def _cells():
    return [{"task": f"t{i}", "task_type": "bugfix", "adapter": "openai_harness",
             "is_harness": True, "success": True, "status": "succeeded", "tool_calls": 2,
             "commands": 1, "file_reads": 1} for i in range(8)]


def _scorer(content, held):
    return 1.0 if "- verify" in content else 0.4


def _proposer(train, current):
    return [] if "- verify" in current else [SkillEdit("append", content="- verify")]


def _improving_job():
    base = SkillDocument(name="bugfix", content="# Skill\n", status=SkillStatus.CANDIDATE,
                         scope=SkillScope(task_type="bugfix", harness="openai_harness"))
    return SkillScopeJob(base=base, cells=_cells(), scorer=_scorer, proposer=_proposer)


def _flat_job():
    base = SkillDocument(name="feature", content="# Skill\n",
                         scope=SkillScope(task_type="feature"))
    return SkillScopeJob(base=base, cells=_cells(), scorer=lambda c, h: 0.5,
                         proposer=lambda t, c: [SkillEdit("append", content="- noise")])


def test_cycle_deploys_improvement_and_records_event(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        rep = run_skill_improvement_cycle(
            EntityStore(s), [_improving_job(), _flat_job()], cycle_id="c1",
            backend=ACPInternalSkillOptBackend(), max_steps=3)
    assert rep.n_scopes == 2 and rep.n_deployed == 1 and rep.n_no_op == 1
    with session_scope(sf) as s:
        dash = skill_dashboard(EntityStore(s))
    assert dash["n_active_skills"] == 1
    assert dash["evolution_by_action"].get("deployed") == 1
    assert dash["evolution_by_action"].get("no_op") == 1
    assert dash["recent_events"]
