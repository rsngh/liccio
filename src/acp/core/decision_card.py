"""Per-task decision card (Alpha 9 capstone — explainable routing).

A `DecisionCard` unifies everything the control plane knows about a task into one
human-readable explanation: the deterministic classification, the viability
assessment (can we attempt it / must a human review it / should we abstain), the
empirically best `(agent, context_strategy)` from the capability matrix (or an
honest "insufficient data" when no cell is sufficiently sampled), the required
verification, and a plain-language rationale.

This is the trust surface: a reviewer can read one card and understand *why* ACP
would route a task the way it would — without overclaiming on thin evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.core.classifier import classify
from acp.core.enums import RiskLevel, TaskType
from acp.core.viability import assess_viability
from acp.routing.capability_matrix import CapabilityMatrix
from acp.schemas.task import Task


@dataclass
class DecisionCard:
    task_id: str
    task_type: str
    risk_level: str
    viable: bool
    abstain: bool
    human_review_required: bool
    true_harness_required: bool
    recommended_agent_class: str | None
    recommended_context_strategy: str | None
    recommendation_basis: str
    required_verification: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "task_type": self.task_type,
            "risk_level": self.risk_level, "viable": self.viable,
            "abstain": self.abstain,
            "human_review_required": self.human_review_required,
            "true_harness_required": self.true_harness_required,
            "recommended_agent_class": self.recommended_agent_class,
            "recommended_context_strategy": self.recommended_context_strategy,
            "recommendation_basis": self.recommendation_basis,
            "required_verification": self.required_verification,
            "rationale": self.rationale,
        }


def build_decision_card(
    task: Task,
    *,
    matrix: CapabilityMatrix | None = None,
    repo_type: str = "python_package",
) -> DecisionCard:
    """Assemble a decision card from classification + viability + capability matrix."""
    cls = classify(task)
    v = assess_viability(task, cls)
    ttype = v.task_type.value if isinstance(v.task_type, TaskType) else str(v.task_type)
    risk = v.risk_level.value if isinstance(v.risk_level, RiskLevel) else str(v.risk_level)

    rationale: list[str] = []
    rationale.append(f"classified as {ttype} / {risk} risk")
    if v.abstain:
        rationale.append("ABSTAIN: " + "; ".join(v.abstention_reasons))
    if v.true_harness_required:
        rationale.append("requires a true tool-loop harness (not a cheap single-shot)")
    if v.human_review_required:
        rationale.append("human review required before merge")

    rec_agent: str | None = None
    rec_strategy: str | None = None
    basis = "no capability matrix supplied"
    if matrix is not None:
        cell, reason = matrix.best_for(ttype, risk, repo_type)
        basis = reason
        if cell is not None:
            rec_agent = cell.agent_class
            rec_strategy = cell.context_strategy
            rationale.append(
                f"capability matrix recommends agent_class={cell.agent_class}, "
                f"strategy={cell.context_strategy} "
                f"(success_rate={cell.success_rate}, n={cell.sample_size})")
        else:
            rationale.append(f"no confident capability cell ({reason}); "
                             "fall back to viability-allowed defaults")
    # Fall back to viability's allowed sets when the matrix can't confidently choose.
    if rec_agent is None and v.viable_agent_classes:
        rec_agent = v.viable_agent_classes[0]
    if rec_strategy is None and v.viable_context_strategies:
        rec_strategy = v.viable_context_strategies[0]

    return DecisionCard(
        task_id=task.id, task_type=ttype, risk_level=risk,
        viable=not v.abstain, abstain=v.abstain,
        human_review_required=v.human_review_required,
        true_harness_required=v.true_harness_required,
        recommended_agent_class=rec_agent,
        recommended_context_strategy=rec_strategy,
        recommendation_basis=basis,
        required_verification=list(v.required_verification),
        rationale=rationale,
    )
