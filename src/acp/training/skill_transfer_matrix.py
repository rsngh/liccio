"""Skill transfer matrix + scope learner (Alpha 30 — skill economy v2).

A skill that helps in one scope can be neutral or actively harmful in another (the Alpha-25
vendor self-catch showed a skill that helped a weak model needed re-checking on a strong
vendor harness). The transfer matrix records, per (skill, target scope), the observed
baseline-vs-skill solve rates and classifies the transfer — robustly (small-sample safe via
two-proportion significance) and activation-aware (an un-activated/degraded measurement is
``untrusted`` and never drives a scope decision). The scope learner then narrows a skill to
the scopes where it ROBUSTLY helps and excludes those where it hurts — the negative-transfer
defense, as a living scope policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.routing.cell_statistics import robustly_better, two_proportion_significant

VERDICTS = ("helps", "neutral", "hurts", "untrusted")


@dataclass
class TransferCell:
    skill_id: str
    target_scope: str                  # e.g. "harness:claude_code" or "task_type:bugfix"
    baseline_successes: int
    baseline_n: int
    skill_successes: int
    skill_n: int
    activation_rate: float = 1.0       # measurement trust: degraded run -> untrusted

    def lift(self) -> float:
        b = self.baseline_successes / self.baseline_n if self.baseline_n else 0.0
        s = self.skill_successes / self.skill_n if self.skill_n else 0.0
        return round(s - b, 4)


def transfer_verdict(cell: TransferCell, *, min_activation: float = 0.8) -> str:
    """Classify a skill's transfer to a scope: helps | neutral | hurts | untrusted."""
    if cell.activation_rate < min_activation or cell.skill_n == 0 or cell.baseline_n == 0:
        return "untrusted"
    if robustly_better(cell.skill_successes, cell.skill_n,
                       cell.baseline_successes, cell.baseline_n):
        return "helps"
    if robustly_better(cell.baseline_successes, cell.baseline_n,
                       cell.skill_successes, cell.skill_n):
        return "hurts"
    # a non-robust difference (or none) -> neutral, unless significant the other way
    if (cell.lift() < 0 and two_proportion_significant(
            cell.skill_successes, cell.skill_n, cell.baseline_successes, cell.baseline_n)):
        return "hurts"
    return "neutral"


@dataclass
class ScopeRecommendation:
    skill_id: str
    include: list = field(default_factory=list)   # scopes where the skill robustly helps
    exclude: list = field(default_factory=list)   # scopes where it hurts
    unknown: list = field(default_factory=list)   # neutral / untrusted -> keep measuring

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class SkillTransferMatrix:
    """Per-(skill, scope) transfer verdicts + a learned scope recommendation."""

    def __init__(self) -> None:
        self._cells: dict[tuple[str, str], TransferCell] = {}

    def add(self, cell: TransferCell) -> None:
        self._cells[(cell.skill_id, cell.target_scope)] = cell

    def verdict(self, skill_id: str, scope: str) -> str | None:
        c = self._cells.get((skill_id, scope))
        return transfer_verdict(c) if c else None

    def recommended_scope(self, skill_id: str) -> ScopeRecommendation:
        rec = ScopeRecommendation(skill_id=skill_id)
        for (sid, scope), cell in self._cells.items():
            if sid != skill_id:
                continue
            v = transfer_verdict(cell)
            if v == "helps":
                rec.include.append(scope)
            elif v == "hurts":
                rec.exclude.append(scope)
            else:
                rec.unknown.append(scope)
        for lst in (rec.include, rec.exclude, rec.unknown):
            lst.sort()
        return rec

    def summary(self) -> dict:
        from collections import Counter
        verdicts = [transfer_verdict(c) for c in self._cells.values()]
        return {"n_cells": len(self._cells), "by_verdict": dict(Counter(verdicts)),
                "skills": sorted({sid for sid, _ in self._cells})}
