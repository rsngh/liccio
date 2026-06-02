"""Viability assessment (Alpha 7, WS1).

Before routing chooses *how* to attempt a task, the control plane decides *whether
and with what class of resources* the task is viable to automate at all. A
`ViabilityAssessment` is produced by the classification node from deterministic
task signals (type, risk, ambiguity, testability) and consumed by routing as a
hard constraint: it narrows the viable agent classes / context strategies, marks
whether a cheap model suffices or a true harness is required, whether human review
is mandatory, and — crucially — whether the system should **abstain** (decline to
auto-attempt) and why.

This makes "decision quality" a first-class, inspectable object: every run records
what the platform thought was possible and the reasons behind it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from acp.core.enums import RiskLevel, TaskType
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class CapabilityRequirement(ACPModel):
    """A single capability the task demands of whatever attempts it."""

    name: str  # e.g. "write_files", "run_tests", "multi_file_edit", "spec_inference"
    required: bool = True
    reason: str = ""


class ModelStrengthRequirement(ACPModel):
    """How strong a model the task needs (cheap single-shot vs frontier harness)."""

    cheap_model_viable: bool = True
    true_harness_required: bool = False
    min_capability_tier: str = "basic"  # basic | standard | frontier
    reason: str = ""


class ViabilityAssessment(ACPModel):
    id: str = Field(default_factory=lambda: new_id("viability"))
    task_id: str
    repo_id: str | None = None
    task_type: TaskType
    risk_level: RiskLevel

    # Signals (0..1)
    ambiguity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    testability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    available_evidence: list[str] = Field(default_factory=list)

    # Decisions
    viable_agent_classes: list[str] = Field(default_factory=list)
    viable_context_strategies: list[str] = Field(default_factory=list)
    required_verification: list[str] = Field(default_factory=list)
    capability_requirements: list[CapabilityRequirement] = Field(default_factory=list)
    model_strength: ModelStrengthRequirement = Field(default_factory=ModelStrengthRequirement)

    cheap_model_viable: bool = True
    true_harness_required: bool = False
    human_review_required: bool = False
    parallelism_recommended: int = 1

    # Abstention
    abstain: bool = False
    abstention_reasons: list[str] = Field(default_factory=list)

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    supporting_features: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    def summary(self) -> str:
        if self.abstain:
            return f"abstain: {', '.join(self.abstention_reasons) or 'unspecified'}"
        return (f"viable via {self.viable_agent_classes} "
                f"(harness_required={self.true_harness_required}, "
                f"human_review={self.human_review_required})")
