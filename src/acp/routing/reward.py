"""Reward computation (charter §16.1).

Configurable reward with stored components. Default weights match the charter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from acp.schemas.agent import AgentAttempt
from acp.schemas.evaluation import EvaluationResult
from acp.schemas.learning import RewardEvent


@dataclass
class RewardWeights:
    task_success: float = 3.0
    spec_compliance: float = 1.0
    test_adequacy: float = 0.8
    maintainability: float = 0.4
    token_cost: float = -0.5
    latency: float = -0.3
    review_burden: float = -0.7
    regression_risk: float = -1.5
    security_risk: float = -2.0
    reverted_or_incident: float = -5.0


def compute_reward(
    evaluation: EvaluationResult,
    attempt: AgentAttempt,
    task_success: bool,
    reverted_or_incident: bool = False,
    latency_penalty: float | None = None,
    weights: RewardWeights | None = None,
    label_source: str = "objective",
) -> RewardEvent:
    w = weights or RewardWeights()
    latency = (
        latency_penalty if latency_penalty is not None else min(1.0, attempt.wall_time_s / 600)
    )
    components = {
        "task_success": w.task_success * (1.0 if task_success else 0.0),
        "spec_compliance": w.spec_compliance * evaluation.spec_compliance,
        "test_adequacy": w.test_adequacy * evaluation.test_adequacy,
        "maintainability": w.maintainability * evaluation.maintainability,
        "token_cost": w.token_cost * math.log1p(attempt.estimated_cost_usd),
        "latency": w.latency * latency,
        "review_burden": w.review_burden * evaluation.review_burden,
        "regression_risk": w.regression_risk * evaluation.regression_risk,
        "security_risk": w.security_risk * evaluation.security_risk,
        "reverted_or_incident": w.reverted_or_incident * (1.0 if reverted_or_incident else 0.0),
    }
    total = sum(components.values())
    return RewardEvent(
        task_id=evaluation.task_id,
        attempt_id=attempt.id,
        routing_decision_id=attempt.routing_decision_id,
        reward=round(total, 6),
        components={k: round(v, 6) for k, v in components.items()},
        label_source=label_source,
    )
