"""Unified self-improvement overview + next-target ranking (Round 20)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.skill import SkillDocument, SkillScope
from acp.schemas.skill_evolution import SkillEvolutionEvent
from acp.training.skill_overview import next_optimization_targets, self_improvement_overview
from acp.training.skill_registry import save_skill


def _sf(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'ov.db'}")
    create_all(e)
    return make_session_factory(e)


def test_next_target_prioritizes_scope_without_skill(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), SkillDocument(
            name="bugfix", content="x", status=SkillStatus.ACTIVE, version=2,
            scope=SkillScope(task_type="bugfix")))
    scopes = [SkillScope(task_type="bugfix").key(), SkillScope(task_type="feature").key()]
    with session_scope(sf) as s:
        targets = next_optimization_targets(EntityStore(s), scopes)
    # feature (no skill) ranks above bugfix (recently improved).
    assert targets[0]["scope"] == SkillScope(task_type="feature").key()
    assert targets[0]["priority"] == 3


def test_plateaued_scope_ranks_above_recently_improved(tmp_path) -> None:
    sf = _sf(tmp_path)
    plateau = SkillScope(task_type="docs").key()
    improved = SkillScope(task_type="bugfix").key()
    with session_scope(sf) as s:
        es = EntityStore(s)
        for sk in (("docs", plateau), ("bugfix", improved)):
            save_skill(es, SkillDocument(name=sk[0], content="x", version=2,
                                         status=SkillStatus.ACTIVE,
                                         scope=SkillScope(task_type=sk[0])))
        es.save(SkillEvolutionEvent(scope_key=plateau, action="no_op"),
                extra_index={"scope_key": plateau, "action": "no_op"})
        es.save(SkillEvolutionEvent(scope_key=improved, action="deployed"),
                extra_index={"scope_key": improved, "action": "deployed"})
    with session_scope(sf) as s:
        targets = next_optimization_targets(EntityStore(s), [plateau, improved])
    assert targets[0]["scope"] == plateau and targets[0]["priority"] == 2


def test_overview_combines_skills_and_targets(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), SkillDocument(
            name="bugfix", content="x", status=SkillStatus.ACTIVE,
            scope=SkillScope(task_type="bugfix")))
    with session_scope(sf) as s:
        ov = self_improvement_overview(
            EntityStore(s), candidate_scopes=[SkillScope(task_type="feature").key()],
            learned_models={"promotions": {}})
    assert ov["n_active_skills"] == 1
    assert ov["next_optimization_targets"][0]["priority"] == 3
    assert "learned_models" in ov
