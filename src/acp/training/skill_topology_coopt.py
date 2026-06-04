"""Topology + skill co-optimization (Alpha 21 WS15).

Topology (workflow shape / skip:X) and skill (procedural guidance) interact: skipping the
reviewer is fine WITH a strong verify-skill but risky without it. So they should be chosen
JOINTLY, not independently. Given measured (topology, skill) arms, this picks the
cost-optimal arm whose success holds and whose topology is safe for the task — evaluating
the combination, with the safety gate always overriding evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.routing.topology_safety import filter_topology

SUCCESS_TOLERANCE = 0.02
MIN_ARM_SAMPLE = 3


@dataclass
class CoOptArm:
    topology: list[str]      # [] == full shape
    skill_id: str | None
    success_rate: float
    cost: float
    sample_size: int = 0


@dataclass
class CoOptChoice:
    topology: list[str]
    skill_id: str | None
    reason: str
    cost_saving: float = 0.0


def cooptimize(
    arms: list[CoOptArm], task_type: str, risk_level: str,
) -> CoOptChoice:
    """Pick the cheapest SAFE (topology, skill) arm whose success holds vs the full-shape
    baseline. Unsafe topologies are filtered first (safety overrides evidence)."""
    full = max((a for a in arms if not a.topology), key=lambda a: a.success_rate,
               default=None)
    baseline_success = full.success_rate if full else (
        max((a.success_rate for a in arms), default=0.0))
    baseline_cost = full.cost if full else 0.0

    best = CoOptChoice(topology=[], skill_id=(full.skill_id if full else None),
                       reason="full shape (no safe cheaper arm)")
    best_cost = baseline_cost if full else float("inf")
    for arm in arms:
        if arm.sample_size < MIN_ARM_SAMPLE:
            continue
        safe_topo, _ = filter_topology(arm.topology, task_type, risk_level)
        if set(safe_topo) != set(arm.topology):
            continue  # evidence describes an unsafe shape we can't run
        if arm.success_rate < baseline_success - SUCCESS_TOLERANCE:
            continue
        if arm.cost < best_cost:
            best_cost = arm.cost
            best = CoOptChoice(
                topology=list(arm.topology), skill_id=arm.skill_id,
                reason=(f"cheapest safe (topology+skill) arm holding success "
                        f"{arm.success_rate:.2f} vs {baseline_success:.2f}"),
                cost_saving=round(max(0.0, baseline_cost - arm.cost), 6) if full else 0.0)
    return best
