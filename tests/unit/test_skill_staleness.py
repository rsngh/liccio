"""Skill staleness detector (Alpha 28)."""

from __future__ import annotations

import pytest

from acp.training.skill_staleness import (
    SkillUsageRecord,
    StalenessVerdict,
    audit_skill_library,
    detect_staleness,
)


def _rec(**kw):
    base = {"skill_id": "s1", "last_validated_at": 0.0, "validated_gain": 0.2,
            "uses_since_validation": 10, "recent_solve_rate": 0.9,
            "baseline_solve_rate": 0.7}
    base.update(kw)
    return SkillUsageRecord(**base)


def test_fresh_helpful_skill_is_kept() -> None:
    v = detect_staleness(_rec(), now=10.0)
    assert v.action == "keep" and not v.reasons


def test_aged_skill_is_revalidated() -> None:
    v = detect_staleness(_rec(last_validated_at=0.0), now=200.0)
    assert v.action == "revalidate"


def test_too_many_uses_triggers_revalidation() -> None:
    v = detect_staleness(_rec(uses_since_validation=500), now=10.0)
    assert v.action == "revalidate"


def test_skill_that_stopped_helping_narrows_scope() -> None:
    v = detect_staleness(_rec(recent_solve_rate=0.68, baseline_solve_rate=0.7), now=10.0)
    assert v.action == "narrow_scope"  # small negative lift


def test_harmful_skill_is_retired() -> None:
    v = detect_staleness(_rec(recent_solve_rate=0.5, baseline_solve_rate=0.8), now=10.0)
    assert v.action == "retire"  # lift -0.3 <= retire floor


def test_most_severe_action_wins() -> None:
    # aged AND harmful -> retire (more severe than revalidate)
    v = detect_staleness(_rec(last_validated_at=0.0, recent_solve_rate=0.5,
                              baseline_solve_rate=0.8), now=500.0)
    assert v.action == "retire" and len(v.reasons) >= 2


def test_audit_summarizes_actions() -> None:
    recs = [_rec(skill_id="a"), _rec(skill_id="b", recent_solve_rate=0.5,
                                     baseline_solve_rate=0.8)]
    a = audit_skill_library(recs, now=10.0)
    assert a["n_skills"] == 2 and a["needs_attention"] == 1
    assert a["by_action"]["retire"] == 1


def test_bad_action_rejected() -> None:
    with pytest.raises(ValueError):
        StalenessVerdict("s", "delete_everything", [])
