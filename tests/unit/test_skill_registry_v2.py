"""Skill registry v2 fields (Alpha 21 WS2)."""

from __future__ import annotations

from acp.core.enums import SkillStatus
from acp.schemas.skill import SkillDocument, SkillScope


def test_v2_fields_default_safely() -> None:
    s = SkillDocument(name="s", content="# x\n", scope=SkillScope(task_type="bugfix"))
    assert s.risk_class == "low" and s.deployment_state == "registered"
    assert s.validation_history == [] and s.negative_transfer_history == []
    assert s.required_tools == [] and s.allowed_repositories == []


def test_v2_audit_history_roundtrips() -> None:
    s = SkillDocument(
        name="sec", content="# verify\n", status=SkillStatus.ACTIVE, risk_class="high",
        scope=SkillScope(task_type="security_fix"), required_tools=["run_command"],
        allowed_repositories=["repo_a"], validation_history=[0.5, 0.8, 1.0],
        negative_transfer_history=["feature|*"], deployment_state="active",
        rollback_pointer="skill_old")
    d = s.model_dump(mode="json")
    assert d["risk_class"] == "high" and d["validation_history"] == [0.5, 0.8, 1.0]
    assert d["rollback_pointer"] == "skill_old" and d["deployment_state"] == "active"
    # round-trip
    s2 = SkillDocument(**d)
    assert s2.required_tools == ["run_command"] and s2.allowed_repositories == ["repo_a"]
