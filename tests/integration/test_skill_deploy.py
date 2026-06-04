"""Governed skill deployment + rollback (Round 16)."""

from __future__ import annotations

import acp.db.models  # noqa: F401 - register tables
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_deploy import deploy_skill, rollback_skill
from acp.training.skill_registry import active_skill_for, list_skills, save_skill


def _sf(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'd.db'}")
    create_all(e)
    return make_session_factory(e)


def _skill(version=1, content="# v\n- x\n", status=SkillStatus.ACTIVE):
    return SkillDocument(name="bugfix", content=content, version=version, status=status,
                         scope=SkillScope(task_type="bugfix", harness="openai_harness"))


def test_deploy_blocks_without_canary_gain(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        res = deploy_skill(EntityStore(s), _skill(version=2), canary_score=0.5,
                           baseline_score=0.6)
    assert not res.deployed and res.blocked_reasons


def test_deploy_archives_prior_and_activates(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), _skill(version=1, content="# v1\n"))
    with session_scope(sf) as s:
        res = deploy_skill(EntityStore(s), _skill(version=2, content="# v2 better\n"),
                           canary_score=1.0, baseline_score=0.5)
    assert res.deployed and res.version == 2 and res.rollback_to is not None
    with session_scope(sf) as s:
        es = EntityStore(s)
        active = active_skill_for(es, task_type="bugfix", harness="openai_harness")
        assert active is not None and active.version == 2
        archived = list_skills(es, status=SkillStatus.ARCHIVED)
        assert len(archived) == 1 and archived[0].version == 1


def test_rollback_restores_prior(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), _skill(version=1, content="# v1\n"))
    with session_scope(sf) as s:
        deploy_skill(EntityStore(s), _skill(version=2, content="# v2\n"),
                     canary_score=1.0, baseline_score=0.5)
    with session_scope(sf) as s:
        es = EntityStore(s)
        scope_key = active_skill_for(es, task_type="bugfix",
                                     harness="openai_harness").scope.key()
        res = rollback_skill(es, scope_key)
    assert res.deployed and res.version == 1
    with session_scope(sf) as s:
        active = active_skill_for(EntityStore(s), task_type="bugfix",
                                  harness="openai_harness")
        assert active.version == 1
