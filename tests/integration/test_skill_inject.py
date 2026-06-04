"""Skill-aware context injection (Round 16)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_inject import inject_active_skill, inject_skill
from acp.training.skill_registry import save_skill


def _sf(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path / 'i.db'}")
    create_all(e)
    return make_session_factory(e)


def _pack():
    return ContextPack(repo_id="r", task_id="t", snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path="a.py", content="x")])


def test_inject_none_is_unchanged() -> None:
    p = _pack()
    assert inject_skill(p, None) is p


def test_inject_active_skill_prepends(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), SkillDocument(
            name="bugfix", content="- run tests before finishing", status=SkillStatus.ACTIVE,
            scope=SkillScope(task_type="bugfix", harness="openai_harness")))
    with session_scope(sf) as s:
        pack, skill = inject_active_skill(EntityStore(s), _pack(), task_type="bugfix",
                                          harness="openai_harness")
    assert skill is not None
    assert pack.items[0].path == "SKILL.md" and "run tests" in pack.items[0].content
    assert len(pack.items) == 2  # skill + original


def test_no_active_skill_for_scope_returns_original(tmp_path) -> None:
    sf = _sf(tmp_path)
    with session_scope(sf) as s:
        pack, skill = inject_active_skill(EntityStore(s), _pack(), task_type="feature")
    assert skill is None and len(pack.items) == 1
