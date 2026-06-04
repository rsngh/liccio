"""Relative trajectory judging for skill updates (Alpha 21 WS16).

Solve-rate is one signal that a skill helped; the relative trajectory judge adds eight
more (goal achievement, test adequacy, minimality, security, harness activation/adherence,
recovery, cost). This judges a WITH-skill trajectory against a WITHOUT-skill trajectory on
the same task, so a skill that solves equally but is cleaner / cheaper / more secure is
recognized — and one that solves but regresses on security/minimality is flagged.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.evaluation.trajectory_judge import RelativeTrajectoryJudge
from acp.schemas.trace import AgentTrace


@dataclass
class SkillTrajectoryVerdict:
    skill_improved_trajectory: bool
    overall_winner: str            # "a" (without) | "b" (with) | "tie"
    per_axis: dict[str, str]       # axis -> winner
    regressed_axes: list[str]      # axes where WITH-skill is worse


def judge_skill_update(
    without_trace: AgentTrace, with_trace: AgentTrace, *,
    solved_without: bool = False, solved_with: bool = False,
    diff_without=None, diff_with=None,
) -> SkillTrajectoryVerdict:
    """Judge a WITH-skill trajectory (b) vs WITHOUT-skill (a) on the eight axes."""
    judge = RelativeTrajectoryJudge()
    comp = judge.compare(without_trace, with_trace, solved_a=solved_without,
                         solved_b=solved_with, diff_a=diff_without, diff_b=diff_with)
    per_axis = {r.axis: str(r.winner) for r in comp.per_axis}
    regressed = [r.axis for r in comp.per_axis if r.winner == "a"]
    return SkillTrajectoryVerdict(
        skill_improved_trajectory=(comp.overall_winner == "b"),
        overall_winner=comp.overall_winner, per_axis=per_axis, regressed_axes=regressed)
