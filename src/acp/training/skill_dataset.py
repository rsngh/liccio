"""Trusted SkillOpt dataset builder (Alpha 15 WS4).

A SkillOpt run learns from *evidence*: which tasks the frozen agent solved or failed.
ACP only lets TRUSTED evidence in — conclusive attempts (via the learning gate), never
contaminated/infra/inconclusive ones — so a skill is never optimized toward noise. The
dataset is split into a train slice (edits are proposed from its failures/successes) and
a held-out slice (the validation gate scores candidates on it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.evaluation.learning_gate import eligible_for_quality
from acp.evaluation.measurement_hygiene import classify_attempt


@dataclass
class SkillTask:
    """One trusted, conclusive task observation used as SkillOpt evidence."""

    task_id: str
    task_type: str
    solved: bool
    reason: str = ""
    adapter: str = ""


@dataclass
class SkillDataset:
    train: list[SkillTask] = field(default_factory=list)
    held_out: list[SkillTask] = field(default_factory=list)
    excluded_contaminated: int = 0

    @property
    def n(self) -> int:
        return len(self.train) + len(self.held_out)


def build_skill_dataset(cells: list[Any], *, held_out_frac: float = 0.4) -> SkillDataset:
    """Build a trusted, split SkillOpt dataset from attempt cells.

    Contaminated/inconclusive attempts are EXCLUDED (the WS2 hard invariant): only
    conclusive outcomes become evidence. The split is deterministic (every k-th item
    to held-out) so a run is reproducible.
    """
    excluded = sum(1 for c in cells if not eligible_for_quality(c))
    trusted = [c for c in cells if eligible_for_quality(c)]
    tasks: list[SkillTask] = []
    for c in trusted:
        outcome = classify_attempt(c)
        tasks.append(SkillTask(
            task_id=str(_get(c, "task") or _get(c, "task_id") or _get(c, "attempt_id") or "t"),
            task_type=str(_get(c, "task_type", "unknown") or "unknown"),
            solved=outcome.is_success,
            reason=str(_get(c, "error") or ""),
            adapter=str(_get(c, "adapter", "") or "")))
    if not tasks:
        return SkillDataset(excluded_contaminated=excluded)
    stride = max(2, round(1 / held_out_frac)) if held_out_frac > 0 else 0
    train: list[SkillTask] = []
    held: list[SkillTask] = []
    for i, t in enumerate(tasks):
        (held if stride and (i % stride == 0) else train).append(t)
    # Guarantee both slices are non-empty when we have >= 2 tasks.
    if not held and len(train) > 1:
        held.append(train.pop())
    if not train and len(held) > 1:
        train.append(held.pop())
    return SkillDataset(train=train, held_out=held, excluded_contaminated=excluded)


def _get(cell: Any, key: str, default: Any = None) -> Any:
    if isinstance(cell, dict):
        return cell.get(key, default)
    return getattr(cell, key, default)
