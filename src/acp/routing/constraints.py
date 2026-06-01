"""Hard routing constraints (charter §13.6)."""

from __future__ import annotations

from acp.core.enums import RiskLevel
from acp.schemas.routing import RoutingAction


def apply_constraints(
    candidates: list[RoutingAction],
    risk: RiskLevel,
    available_agents: set[str],
    max_cost_usd: float,
    max_parallelism: int = 4,
    experimental_policy: bool = False,
) -> tuple[list[RoutingAction], list[str]]:
    """Filter/clamp candidate actions against hard constraints.

    Returns (filtered_actions, applied_constraint_names).
    """
    applied: list[str] = []
    out: list[RoutingAction] = []
    for a in candidates:
        if a.agent_name not in available_agents:
            applied.append(f"removed_unavailable:{a.agent_name}")
            continue
        action = a.model_copy(deep=True)
        if action.max_cost_usd > max_cost_usd:
            action.max_cost_usd = max_cost_usd
            applied.append("clamped_cost")
        if action.parallelism > max_parallelism:
            action.parallelism = max_parallelism
            applied.append("clamped_parallelism")
        if risk.requires_human_review():
            action.requires_human_approval = True
            applied.append("high_risk_requires_human_review")
        if experimental_policy:
            action.requires_human_approval = True
            applied.append("experimental_policy_cannot_auto_approve")
        out.append(action)
    return out, sorted(set(applied))
