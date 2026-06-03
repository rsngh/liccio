"""Topology-action safety gate (Alpha 11/12 WS14).

Learning the *shape* of the workflow (skip retrieval / planner / reviewer / strict
verification) is a powerful cost lever — but some skips are unsafe for some tasks.
A security fix must never skip strict verification; a high-risk change must never
skip human/automated review. This gate filters a proposed topology against the
task's type and risk so the learned policy can save cost on cheap tasks (docs/lint)
without ever dropping a safety-critical cell on a risky one.
"""

from __future__ import annotations

from acp.core.enums import RiskLevel, TaskType

# Skips that are forbidden when the task is security-sensitive or high-risk.
_SAFETY_CRITICAL_SKIPS = frozenset({
    "skip_strict_verification", "skip_reviewer", "run_light_verifier",
})

# Task types that always demand the strongest verification/review.
_SECURITY_TASKS = frozenset({TaskType.SECURITY_FIX.value, TaskType.MIGRATION.value})
_HIGH_RISK = frozenset({RiskLevel.HIGH.value, RiskLevel.CRITICAL.value})


def is_skip_allowed(action: str, task_type: str, risk_level: str) -> tuple[bool, str | None]:
    """Return (allowed, reason_if_not) for one topology action under task context."""
    tt = str(task_type).lower()
    risk = str(risk_level).lower()
    safety_critical = tt in _SECURITY_TASKS or risk in _HIGH_RISK
    if action in _SAFETY_CRITICAL_SKIPS and safety_critical:
        return False, (f"{action} forbidden for {tt}/{risk} "
                       "(safety-critical: verification/review must not be skipped)")
    return True, None


def filter_topology(
    topology: list[str], task_type: str, risk_level: str
) -> tuple[list[str], dict[str, str]]:
    """Split a proposed topology into (allowed actions, {rejected: reason}).

    The router applies the allowed set; the rejected map explains every dropped
    skip so the decision dossier can show why a cost-saving shape was overridden.
    """
    allowed: list[str] = []
    rejected: dict[str, str] = {}
    for action in topology:
        ok, reason = is_skip_allowed(action, task_type, risk_level)
        if ok:
            allowed.append(action)
        else:
            rejected[action] = reason or "forbidden"
    return allowed, rejected
