"""Skill composition: conflict, ordering, budget (Alpha 21 WS7)."""

from __future__ import annotations

from acp.schemas.skill import SkillDocument, SkillScope
from acp.training.skill_composition import compose_skills


def _skill(name, content, risk="low", score=1.0, version=1):
    return SkillDocument(name=name, content=content, risk_class=risk,
                         held_out_score=score, version=version,
                         scope=SkillScope(task_type=name))


def test_compose_merges_distinct_skills() -> None:
    a = _skill("bugfix_pytest", "# s\n- run pytest before finishing\n")
    b = _skill("minimal_diff", "# s\n- make the minimal change\n")
    res = compose_skills([a, b])
    assert "- run pytest before finishing" in res.content
    assert "- make the minimal change" in res.content
    assert len(res.included) == 2 and not res.excluded


def test_duplicate_directives_deduped() -> None:
    a = _skill("a", "# s\n- run the tests\n")
    b = _skill("b", "# s\n- run the tests\n")  # exact dup
    res = compose_skills([a, b])
    assert res.content.count("- run the tests") == 1
    assert res.conflicts_resolved >= 1


def test_safety_skill_ordered_first() -> None:
    low = _skill("ci", "# s\n- skip slow checks\n", risk="low")
    high = _skill("security", "# s\n- always run the strict verifier\n", risk="high")
    res = compose_skills([low, high])
    # The high-risk (safety) skill's line precedes the low-risk one.
    idx_sec = res.content.index("strict verifier")
    idx_ci = res.content.index("skip slow checks")
    assert idx_sec < idx_ci
    assert res.included[0]["skill_id"] == high.id


def test_contradiction_resolved_in_favor_of_higher_priority() -> None:
    high = _skill("security", "# s\n- always run the verifier\n", risk="high")
    low = _skill("speed", "# s\n- never run the verifier to save time\n", risk="low")
    res = compose_skills([high, low])
    assert "always run the verifier" in res.content
    assert "never run the verifier" not in res.content
    assert low.id in res.excluded and res.conflicts_resolved >= 1


def test_token_budget_excludes_overflow() -> None:
    big = _skill("a", "# s\n" + "\n".join(f"- directive number {i}" for i in range(40)))
    small = _skill("b", "# s\n- one small rule\n")
    res = compose_skills([big, small], token_budget=40)
    # The big skill fits first; the small one overflows the tight budget OR vice versa,
    # but at least one is excluded for budget and the result stays within budget+slack.
    assert res.excluded
    assert any("budget" in r for r in res.excluded.values())
