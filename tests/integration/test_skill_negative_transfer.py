"""Skill negative-transfer campaign + auto-narrowing (Alpha 21 WS10)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.routing.coordination import compose_coordination
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_negative_transfer import (
    applies_to_domain,
    assess_transfer,
    narrow_skill_scope,
)
from acp.training.skill_registry import save_skill


def test_assess_classifies_transfer() -> None:
    a = assess_transfer({"bugfix": (0.5, 1.0), "security_fix": (1.0, 0.6),
                         "docs": (0.8, 0.81)})
    assert a.positive_domains == ["bugfix"]
    assert a.negative_domains == ["security_fix"]
    assert a.neutral_domains == ["docs"]


def test_narrow_records_history_and_excludes() -> None:
    s = SkillDocument(name="verify", content="- run tests",
                      scope=SkillScope(harness="openai_harness"))
    narrowed = narrow_skill_scope(s, ["security_fix"])
    assert "security_fix" in narrowed.negative_transfer_history
    assert not applies_to_domain(narrowed, "security_fix")
    assert applies_to_domain(narrowed, "bugfix")


def test_routing_excludes_negative_transfer_skill(tmp_path) -> None:
    e = make_engine(f"sqlite:///{tmp_path / 'nt.db'}")
    create_all(e)
    sf = make_session_factory(e)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), SkillDocument(
            name="verify", content="# s\n- run tests\n", status=SkillStatus.ACTIVE,
            negative_transfer_history=["security_fix"],
            scope=SkillScope(harness="openai_harness")))  # broad scope (any task_type)
    with session_scope(sf) as s:
        es = EntityStore(s)
        # Applies to bugfix...
        dec_bug = compose_coordination(task_type="bugfix", risk_level="medium",
                                       store=es, harness_hint="openai_harness")
        # ...but excluded for security_fix (negative transfer recorded).
        dec_sec = compose_coordination(task_type="security_fix", risk_level="high",
                                       store=es, harness_hint="openai_harness")
    assert dec_bug.selected_skills and not dec_sec.selected_skills
