"""SkillOpt provenance graph (Alpha 21 WS3).

A durable, auditable record of one optimization run: every candidate (its edits,
held-out validation score, and the gate's accept/reject decision), the base/best scores,
the rollout evidence it learned from, and the final deploy/reject decision. This makes
the acceptance criterion mechanical: *every skill line can be traced to rollout evidence,
an edit proposal, the validation gate, and the promotion decision.*
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class SkillEditRecord(ACPModel):
    op: str
    content: str = ""
    target: str = ""


class SkillCandidateRecord(ACPModel):
    """One candidate skill considered during the run."""

    step: int
    edits: list[SkillEditRecord] = Field(default_factory=list)
    validation_score: float = 0.0
    gate_action: str = "reject"  # accept_new_best | accept | reject


class SkillProvenanceRun(ACPModel):
    """The full lineage of a SkillOpt run."""

    id: str = Field(default_factory=lambda: new_id("skprov"))
    created_at: datetime = Field(default_factory=utcnow)
    skill_name: str
    scope_key: str
    backend: str = ""
    base_score: float = 0.0
    best_score: float = 0.0
    deployable: bool = False
    deployed: bool = False
    candidates: list[SkillCandidateRecord] = Field(default_factory=list)
    n_accepted: int = 0
    n_rejected: int = 0
    evidence_run_ids: list[str] = Field(default_factory=list)
    deployed_skill_id: str | None = None
    decision_reason: str = ""
