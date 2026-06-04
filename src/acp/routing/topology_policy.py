"""Learned topology policy (Alpha 14 WS16).

The safety gate (``topology_safety``) says which workflow-shape skips are *allowed*;
this module learns which allowed skips are *worth taking* from evidence. Given the
observed success-rate and cost of each topology arm for a task class, it recommends
the cheapest safe shape that does not degrade success below the full-shape baseline.
Contaminated measurement is refused as input, so an infra-noisy run can never teach
the router to skip a safety-relevant cell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.routing.topology_safety import filter_topology


@dataclass
class TopologyArm:
    """One observed workflow shape and its evidence for a task class."""

    topology: list[str]  # [] == full shape (no skips)
    success_rate: float
    cost: float
    sample_size: int = 0


@dataclass
class TopologyRecommendation:
    topology: list[str]
    reason: str
    rejected: dict[str, str] = field(default_factory=dict)
    cost_saving: float = 0.0


# A skip must not drop success by more than this vs the full-shape baseline.
SUCCESS_TOLERANCE = 0.02
MIN_ARM_SAMPLE = 3


def recommend_topology(
    task_type: str, risk_level: str, arms: list[TopologyArm],
) -> TopologyRecommendation:
    """Pick the cheapest SAFE topology whose success holds vs the full-shape baseline.

    Safety first: every arm's skips are run through the safety gate, so a
    security/high-risk task can never be recommended an unsafe skip regardless of
    evidence. Among the safe, sufficiently-sampled arms that keep success within
    ``SUCCESS_TOLERANCE`` of the full shape, the lowest-cost one wins.
    """
    # Baseline = the full shape ([]), or the best-sampled arm if no full shape seen.
    full = next((a for a in arms if not a.topology), None)
    baseline_success = full.success_rate if full else (
        max((a.success_rate for a in arms), default=0.0))
    baseline_cost = full.cost if full else 0.0

    best = TopologyRecommendation(topology=[], reason="full shape (no safe cheaper arm)")
    best_cost = baseline_cost if full else float("inf")
    for arm in arms:
        if arm.sample_size < MIN_ARM_SAMPLE:
            continue
        safe_topo, rejected = filter_topology(arm.topology, task_type, risk_level)
        # If the safety gate stripped any skip, this arm's evidence doesn't apply to
        # the shape we could actually run — skip it (its cost reflects unsafe skips).
        if set(safe_topo) != set(arm.topology):
            continue
        if arm.success_rate < baseline_success - SUCCESS_TOLERANCE:
            continue
        if arm.cost < best_cost:
            best_cost = arm.cost
            saving = round(baseline_cost - arm.cost, 6) if full else 0.0
            best = TopologyRecommendation(
                topology=list(arm.topology),
                reason=(f"cheapest safe arm holding success "
                        f"({arm.success_rate:.2f} vs baseline {baseline_success:.2f})"),
                rejected=rejected, cost_saving=max(0.0, saving))
    return best


def should_update_topology_policy(cells: list[Any]) -> bool:
    """False when the run is measurement-contaminated (WS16 safety): a noisy run must
    not teach the topology policy. Ties to the WS1/WS3 measurement-hygiene contract."""
    from acp.evaluation.measurement_hygiene import build_hygiene_report

    if not cells:
        return False
    return not build_hygiene_report(cells).contaminated
