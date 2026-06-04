"""Unified coordination decision: model + topology + skill (Round 17)."""

from __future__ import annotations

import acp.db.models  # noqa: F401
from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.routing.capability_matrix import CapabilityMatrix
from acp.routing.coordination import compose_coordination
from acp.routing.topology_policy import TopologyArm
from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_registry import save_skill


def _matrix():
    rows = [{"task_type": "bugfix", "risk": "medium", "adapter": "openai_harness",
             "is_harness": True, "context_strategy": "hybrid", "success": True,
             "status": "succeeded", "tool_calls": 2, "commands": 1, "file_reads": 1,
             "cost_usd": 0.001} for _ in range(6)]
    return CapabilityMatrix.from_bakeoff_report({"cells": rows})


def test_compose_binds_model_topology_skill(tmp_path) -> None:
    e = make_engine(f"sqlite:///{tmp_path / 'c.db'}")
    create_all(e)
    sf = make_session_factory(e)
    with session_scope(sf) as s:
        save_skill(EntityStore(s), SkillDocument(
            name="bugfix", content="- verify", status=SkillStatus.ACTIVE,
            held_out_score=1.0, version=2,
            scope=SkillScope(task_type="bugfix", harness="openai_harness")))
    arms = [TopologyArm([], 1.0, 0.010, 5),
            TopologyArm(["skip_retrieval"], 1.0, 0.004, 5)]
    with session_scope(sf) as s:
        dec = compose_coordination(task_type="bugfix", risk_level="medium",
                                   repo_type="unknown", matrix=_matrix(),
                                   store=EntityStore(s), topology_arms=arms)
    assert dec.agent_name == "openai_harness"
    assert dec.topology == ["skip_retrieval"]      # cheapest safe shape
    assert dec.skill_version == 2                  # active skill bound
    assert set(dec.rationale) == {"model", "topology", "skill"}


def test_security_topology_safety_in_coordination() -> None:
    arms = [TopologyArm([], 1.0, 0.03, 5),
            TopologyArm(["skip_strict_verification"], 1.0, 0.005, 5)]
    dec = compose_coordination(task_type="security_fix", risk_level="high",
                               harness_hint="claude_harness", topology_arms=arms)
    assert dec.topology == []  # safety gate forbids skipping strict verification
    assert dec.agent_name == "claude_harness"


def test_compose_with_no_evidence_is_safe() -> None:
    dec = compose_coordination(task_type="docs", risk_level="low")
    assert dec.topology == [] and dec.skill_id is None


def test_coordination_composes_skill_set_and_explains(tmp_path) -> None:
    # WS8: routing composes the applicable skill library and explains selected/rejected.
    e = make_engine(f"sqlite:///{tmp_path / 'cs.db'}")
    create_all(e)
    sf = make_session_factory(e)
    with session_scope(sf) as s:
        es = EntityStore(s)
        save_skill(es, SkillDocument(name="bugfix_pytest", content="# s\n- run pytest\n",
                   status=SkillStatus.ACTIVE, held_out_score=1.0,
                   scope=SkillScope(task_type="bugfix")))
        save_skill(es, SkillDocument(name="minimal", content="# s\n- minimal change\n",
                   status=SkillStatus.ACTIVE, held_out_score=0.9,
                   scope=SkillScope(task_type="bugfix")))
    with session_scope(sf) as s:
        dec = compose_coordination(task_type="bugfix", risk_level="medium",
                                   store=EntityStore(s), harness_hint="openai_harness")
    assert len(dec.selected_skills) == 2
    assert "- run pytest" in dec.composed_skill and "- minimal change" in dec.composed_skill
    assert "composed 2 skill" in dec.rationale["skill"]
