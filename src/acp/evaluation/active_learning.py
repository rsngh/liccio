"""Active learning selector (charter §15.5)."""

from __future__ import annotations

from dataclasses import dataclass

from acp.schemas.evaluation import ActiveLearningScore

WEIGHTS = {
    "uncertainty": 0.30,
    "evaluator_disagreement": 0.20,
    "business_risk": 0.20,
    "novelty": 0.10,
    "cost_surprise": 0.10,
    "policy_value_of_information": 0.10,
}


@dataclass
class ALInputs:
    task_id: str
    attempt_id: str | None = None
    uncertainty: float = 0.0
    evaluator_disagreement: float = 0.0
    business_risk: float = 0.0
    novelty: float = 0.0
    cost_surprise: float = 0.0
    policy_value_of_information: float = 0.0
    is_audit_sample: bool = False


class ActiveLearningSelector:
    def __init__(self, threshold: float = 0.25) -> None:
        self.threshold = threshold

    def score(self, x: ALInputs) -> ActiveLearningScore:
        priority = (
            WEIGHTS["uncertainty"] * x.uncertainty
            + WEIGHTS["evaluator_disagreement"] * x.evaluator_disagreement
            + WEIGHTS["business_risk"] * x.business_risk
            + WEIGHTS["novelty"] * x.novelty
            + WEIGHTS["cost_surprise"] * x.cost_surprise
            + WEIGHTS["policy_value_of_information"] * x.policy_value_of_information
        )
        selected = x.is_audit_sample or priority >= self.threshold
        return ActiveLearningScore(
            task_id=x.task_id,
            attempt_id=x.attempt_id,
            priority=round(priority, 4),
            uncertainty=x.uncertainty,
            evaluator_disagreement=x.evaluator_disagreement,
            business_risk=x.business_risk,
            novelty=x.novelty,
            cost_surprise=x.cost_surprise,
            policy_value_of_information=x.policy_value_of_information,
            selected=selected,
            metadata={"audit_sample": x.is_audit_sample},
        )
