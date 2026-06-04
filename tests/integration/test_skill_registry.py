"""Skill registry persistence + scope + diff (Alpha 15 WS2)."""

from __future__ import annotations

import acp.db.models  # noqa: F401 - register tables before create_all
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_registry import (
    active_skill_for,
    diff_skills,
    list_skills,
    save_skill,
)


def _store(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 's.db'}")
    create_all(engine)
    return make_session_factory(engine)


def test_skill_persist_versioned_hashed_scoped(tmp_path) -> None:
    sf = _store(tmp_path)
    skill = SkillDocument(name="bugfix", content="# Skill\n- Read before write.\n",
                          scope=SkillScope(task_type="bugfix", harness="openai_harness"),
                          status=SkillStatus.ACTIVE)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), skill)
    with session_scope(sf) as s:
        got = list_skills(EntityStore(s), status=SkillStatus.ACTIVE)
    assert len(got) == 1
    assert got[0].content_sha == skill.content_sha and got[0].version == 1
    assert got[0].scope.task_type == "bugfix"


def test_active_skill_scope_match(tmp_path) -> None:
    sf = _store(tmp_path)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), SkillDocument(
            name="sec", content="x", status=SkillStatus.ACTIVE,
            scope=SkillScope(task_type="security_fix")))
    with session_scope(sf) as s:
        es = EntityStore(s)
        assert active_skill_for(es, task_type="security_fix") is not None
        assert active_skill_for(es, task_type="bugfix") is None


def test_diff_skills_shows_content_change() -> None:
    a = SkillDocument(name="s", content="line1\nline2\n", version=1)
    b = SkillDocument(name="s", content="line1\nline2 improved\n", version=2)
    d = diff_skills(a, b)
    assert "line2 improved" in d and "v1" in d and "v2" in d
