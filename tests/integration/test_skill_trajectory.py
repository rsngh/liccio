"""Relative trajectory judging for skill updates (Alpha 21 WS16)."""

from __future__ import annotations

from acp.schemas.trace import AgentTrace
from acp.training.skill_trajectory import judge_skill_update


def _trace(**kw) -> AgentTrace:
    base = {"attempt_id": "a", "adapter_name": "openai_harness", "is_harness": True,
            "status": "succeeded", "tool_calls": 4, "file_reads": 2, "commands": 2,
            "changed_files": ["x.py"], "diff_lines": 8, "estimated_cost_usd": 0.001}
    base.update(kw)
    return AgentTrace(**base)


def test_skill_that_adds_verification_improves_trajectory() -> None:
    # WITHOUT: wrote but never ran a command (no verify). WITH: read + wrote + verified.
    without = _trace(tool_calls=1, file_reads=0, commands=0, changed_files=["x.py"])
    with_skill = _trace(tool_calls=5, file_reads=2, commands=2)
    v = judge_skill_update(without, with_skill, solved_without=False, solved_with=True)
    assert v.skill_improved_trajectory and v.overall_winner == "b"


def test_per_axis_and_regressions_reported() -> None:
    without = _trace(tool_calls=3, file_reads=1, commands=1)
    with_skill = _trace(tool_calls=3, file_reads=1, commands=1)
    v = judge_skill_update(without, with_skill, solved_without=True, solved_with=True)
    assert isinstance(v.per_axis, dict) and len(v.per_axis) == 8
    assert isinstance(v.regressed_axes, list)
