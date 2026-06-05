"""Skill staleness detector (Alpha 28 — skill-library hardening).

A deployed skill is not forever-good: the codebase moves, its measured gain can decay, and a
skill that once helped may start hurting on recent traffic (negative transfer creeping in).
This detector flags skills that need attention and recommends an action — revalidate, narrow
scope, or retire — BEFORE damage spreads, so the skill library self-maintains. It is
advisory: it never deletes a skill, it recommends, and the staged-canary / scope-narrowing
machinery acts on the recommendation under governance.
"""

from __future__ import annotations

from dataclasses import dataclass

ACTIONS = ("keep", "revalidate", "narrow_scope", "retire")


@dataclass
class SkillUsageRecord:
    skill_id: str
    last_validated_at: float          # timestamp of last held-out validation
    validated_gain: float             # measured gain at last validation (e.g. +0.2)
    uses_since_validation: int
    recent_solve_rate: float          # solve rate on recent conclusive attempts
    baseline_solve_rate: float        # the scope's no-skill baseline


@dataclass
class StalenessVerdict:
    skill_id: str
    action: str
    reasons: list

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"bad action {self.action}")

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class StalenessPolicy:
    max_age: float = 90.0                 # revalidate after this much idle time
    max_uses_without_validation: int = 200
    min_recent_lift: float = 0.0          # recent skill lift must stay >= this
    negative_lift_retire: float = -0.1    # recent lift this bad -> retire


def detect_staleness(record: SkillUsageRecord, *, now: float,
                     policy: StalenessPolicy | None = None) -> StalenessVerdict:
    """Classify one skill's freshness and recommend an action (most severe wins)."""
    p = policy or StalenessPolicy()
    recent_lift = round(record.recent_solve_rate - record.baseline_solve_rate, 4)
    reasons: list[str] = []
    action = "keep"

    def _escalate(new_action: str, reason: str) -> None:
        nonlocal action
        reasons.append(reason)
        if ACTIONS.index(new_action) > ACTIONS.index(action):
            action = new_action

    age = now - record.last_validated_at
    if age > p.max_age:
        _escalate("revalidate", f"stale: {age:.0f} > {p.max_age} since validation")
    if record.uses_since_validation > p.max_uses_without_validation:
        _escalate("revalidate",
                  f"{record.uses_since_validation} uses without revalidation")
    if recent_lift < p.min_recent_lift:
        # the skill no longer helps on recent traffic -> narrow scope (or retire if bad)
        if recent_lift <= p.negative_lift_retire:
            _escalate("retire", f"recent lift {recent_lift} <= retire floor")
        else:
            _escalate("narrow_scope", f"recent lift {recent_lift} < {p.min_recent_lift}")
    return StalenessVerdict(skill_id=record.skill_id, action=action, reasons=reasons)


def audit_skill_library(records: list, *, now: float,
                        policy: StalenessPolicy | None = None) -> dict:
    """Audit a library of skills; summarize recommended actions."""
    verdicts = [detect_staleness(r, now=now, policy=policy) for r in records]
    from collections import Counter
    by_action = Counter(v.action for v in verdicts)
    return {"n_skills": len(records), "by_action": dict(by_action),
            "needs_attention": sum(1 for v in verdicts if v.action != "keep"),
            "verdicts": [v.to_dict() for v in verdicts]}
