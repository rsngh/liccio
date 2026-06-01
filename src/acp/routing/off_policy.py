"""Off-policy evaluation: IPS and self-normalized IPS (charter §16.5).

Estimates the value of a target policy from logs collected under a behavior
policy. Logs missing valid propensities (action_probability) are rejected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent


class OffPolicyError(ValueError):
    pass


@dataclass
class OPEResult:
    ips: float
    snips: float
    n: int


def _validate(decision: PolicyDecision) -> float:
    p = decision.action_probability
    if p is None or p <= 0.0 or p > 1.0:
        raise OffPolicyError(f"invalid propensity: {p}")
    return p


def evaluate(
    log: list[tuple[PolicyDecision, RewardEvent]],
    target_action_prob: Callable[[PolicyDecision], float],
) -> OPEResult:
    """IPS / SNIPS estimate of a target policy.

    ``target_action_prob`` returns the target policy's probability of the logged
    action under the logged context.
    """
    if not log:
        raise OffPolicyError("empty log")
    num = 0.0
    weight_sum = 0.0
    for decision, reward in log:
        behavior_p = _validate(decision)
        target_p = target_action_prob(decision)
        w = target_p / behavior_p
        num += w * reward.reward
        weight_sum += w
    n = len(log)
    ips = num / n
    snips = num / weight_sum if weight_sum > 0 else 0.0
    return OPEResult(ips=round(ips, 6), snips=round(snips, 6), n=n)
