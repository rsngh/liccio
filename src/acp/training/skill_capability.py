"""Skill capability matrix (Alpha 21 WS9).

The capability matrix answers "which MODEL works for this task?"; this answers "which
SKILL works for this task/harness/repo type?" — aggregating per-(skill, task_type, harness)
the success rate, cost, harness-benefit (HAR/HFR/PWL), measurement quality, and negative
transfer, from attempt cells that carry a skill_id. Routing can then pick the skill family
with the best validated benefit for a scope, not just the most-recently-deployed one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SkillCapabilityCell:
    skill_id: str
    skill_family: str
    task_type: str
    harness: str
    n: int = 0
    success_rate: float = 0.0
    cost: float = 0.0
    har: float = 0.0
    hfr: float = 0.0
    pwl: float = 0.0
    measurement_quality: float = 1.0


def build_skill_capability(cells: list[Any]) -> list[SkillCapabilityCell]:
    """Aggregate skill-tagged attempt cells into per-(skill, task, harness) cells.

    Only cells carrying a ``skill_id`` and a conclusive outcome contribute (infra noise
    is excluded via the measurement-trust classifier).
    """
    from acp.evaluation.learning_gate import eligible_for_quality
    from acp.evaluation.measurement_quality import score_measurement_quality

    groups: dict[tuple, list[dict]] = {}
    for c in cells:
        sid = c.get("skill_id")
        if not sid or not eligible_for_quality(c):
            continue
        key = (sid, c.get("task_type", "unknown"), c.get("adapter", "unknown"))
        groups.setdefault(key, []).append(c)
    out: list[SkillCapabilityCell] = []
    for (sid, tt, harness), rows in groups.items():
        n = len(rows)
        activated = [r for r in rows if r.get("tool_calls", 0) > 0]
        followed = [r for r in activated
                    if r.get("file_reads", 0) > 0 and r.get("commands", 0) > 0]
        out.append(SkillCapabilityCell(
            skill_id=sid, skill_family=str(rows[0].get("skill_family", sid)),
            task_type=tt, harness=harness, n=n,
            success_rate=round(sum(1 for r in rows if r.get("success")) / n, 4),
            cost=round(sum(float(r.get("cost_usd", 0.0)) for r in rows) / n, 6),
            har=round(len(activated) / n, 4),
            hfr=round(len(followed) / n, 4),
            pwl=round(sum(1 for r in activated if r.get("success")) / len(activated), 4)
            if activated else 0.0,
            measurement_quality=score_measurement_quality(rows).overall))
    return out


def best_skill_for(
    cells: list[SkillCapabilityCell], task_type: str, harness: str, *, min_n: int = 3,
) -> SkillCapabilityCell | None:
    """The best-performing sufficiently-sampled skill for a task/harness, by success
    then cost — answering 'which skill works here?'."""
    matching = [c for c in cells if c.task_type == task_type and c.harness == harness
                and c.n >= min_n]
    if not matching:
        return None
    return max(matching, key=lambda c: (c.success_rate, -c.cost))


def skill_capability_table(cells: list[Any]) -> dict:
    """Answer 'which skill works best for each (vendor harness, task type)?' (WS17).

    Returns {harness: {task_type: {skill_id, success_rate, cost, har, hfr, pwl,
    measurement_quality, n}}} from skill-tagged conclusive attempt cells — so the matrix
    spans vendor-native harnesses (codex_cli / claude_code) the same as in-process ones.
    """
    caps = build_skill_capability(cells)
    table: dict = {}
    by_scope: dict[tuple[str, str], list[SkillCapabilityCell]] = {}
    for c in caps:
        by_scope.setdefault((c.harness, c.task_type), []).append(c)
    for (harness, tt), group in by_scope.items():
        best = max(group, key=lambda c: (c.success_rate, -c.cost))
        table.setdefault(harness, {})[tt] = {
            "skill_id": best.skill_id, "skill_family": best.skill_family,
            "success_rate": best.success_rate, "cost": best.cost, "har": best.har,
            "hfr": best.hfr, "pwl": best.pwl,
            "measurement_quality": best.measurement_quality, "n": best.n}
    return table
