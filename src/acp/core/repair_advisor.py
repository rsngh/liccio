"""Repair-driven retry advisor (Alpha 9).

When a first attempt fails, ACP should not blindly retry the same way. The
`RepairAdvisor` classifies the failure (via the repair-strategy classifier), then
maps the diagnosed strategy to a *concrete* next action: which context strategy to
switch to, whether to escalate to a human / abstain, whether a true harness is
required, and a short rationale. This turns the repair taxonomy (WS5) into an
actionable second-attempt plan that orchestration can consult.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.evaluation.repair_classifier import RepairFailureTaxonomy, RuleRepairClassifier
from acp.schemas.task import Task, TaskClassification
from acp.schemas.trace import AgentTrace

# strategy -> (context_strategy hint, escalate_to_human, harness_required, retryable)
_PLAYBOOK: dict[str, tuple[str, bool, bool, bool]] = {
    "logic_fix": ("bug_reproduction", False, False, True),
    "test_addition": ("test_focused", False, False, True),
    "test_repair": ("test_focused", False, False, True),
    "dependency_update": ("minimal", False, False, True),
    "migration_fix": ("architecture", True, True, True),
    "security_remediation": ("architecture", True, True, True),
    "prompt_injection_reject": ("minimal", True, False, False),
    "needs_spec": ("minimal", True, False, False),
    "not_automatable": ("minimal", True, False, False),
}


@dataclass
class RetryAdvice:
    repair_strategy: str
    retryable: bool
    recommended_context_strategy: str
    escalate_to_human: bool
    true_harness_required: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "repair_strategy": self.repair_strategy,
            "retryable": self.retryable,
            "recommended_context_strategy": self.recommended_context_strategy,
            "escalate_to_human": self.escalate_to_human,
            "true_harness_required": self.true_harness_required,
            "reasons": self.reasons,
        }


class RepairAdvisor:
    def __init__(self, classifier: RuleRepairClassifier | None = None) -> None:
        self.classifier = classifier or RuleRepairClassifier()

    def advise(
        self,
        task: Task,
        *,
        classification: TaskClassification | None = None,
        trace: AgentTrace | None = None,
        failure_output: str = "",
    ) -> RetryAdvice:
        strategy, reasons = self.classifier.classify(
            task, classification=classification, trace=trace, failure_output=failure_output)
        ctx, escalate, harness, retryable = _PLAYBOOK.get(
            strategy, ("hybrid_keyword_embedding", True, False, False))
        advice_reasons = [f"diagnosed repair strategy: {strategy}", *reasons]
        if not retryable:
            advice_reasons.append("not safely retryable by an agent — escalate/abstain")
        return RetryAdvice(
            repair_strategy=strategy, retryable=retryable,
            recommended_context_strategy=ctx, escalate_to_human=escalate,
            true_harness_required=harness, reasons=advice_reasons,
        )


def repair_strategies() -> frozenset[str]:
    return RepairFailureTaxonomy.labels()
