"""Skill document registry schemas (Alpha 15 WS2).

A *skill* is a compact, inspectable procedural document (markdown) that is external
state for a FROZEN agent/harness — the SkillOpt idea. ACP versions, hashes, scopes,
and governs skills so an optimized skill is auditable and rollbackable, never a silent
prompt mutation. Scope binds a skill to the routing context it was learned for.
"""

from __future__ import annotations

import hashlib

from pydantic import Field

from acp.core.enums import SkillStatus
from acp.core.ids import new_id
from acp.schemas.base import ACPModel


class SkillScope(ACPModel):
    """The routing context a skill is bound to. ``None`` on a field means "any"."""

    task_type: str | None = None
    risk_level: str | None = None
    repo_type: str | None = None
    harness: str | None = None
    model_family: str | None = None
    context_strategy: str | None = None
    verification_policy: str | None = None

    def key(self) -> str:
        """Stable scope identity (pipe-joined, '*' for any)."""
        fields = (self.task_type, self.risk_level, self.repo_type, self.harness,
                  self.model_family, self.context_strategy, self.verification_policy)
        return "|".join(f or "*" for f in fields)

    def matches(self, *, task_type: str | None = None, risk_level: str | None = None,
                harness: str | None = None, model_family: str | None = None) -> bool:
        """True if this scope is compatible with the given routing context (a None
        scope field is a wildcard that matches anything)."""
        for mine, theirs in ((self.task_type, task_type), (self.risk_level, risk_level),
                             (self.harness, harness), (self.model_family, model_family)):
            if mine is not None and theirs is not None and mine != theirs:
                return False
        return True


def content_hash(content: str) -> str:
    """Deterministic content hash (sha256, first 16 hex) for dedup/audit."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class SkillDocument(ACPModel):
    """A versioned, hashed, scoped skill document.

    ``content`` is the compact markdown skill; ``version`` increments per accepted
    edit; ``parent_id`` links the lineage; ``held_out_score`` is the validation score
    that justified this version; ``provenance`` lists the conclusive evidence the
    skill was learned from (never contaminated traces — see the dataset builder).
    """

    id: str = Field(default_factory=lambda: new_id("skill"))
    name: str
    content: str = ""
    scope: SkillScope = Field(default_factory=SkillScope)
    version: int = 1
    parent_id: str | None = None
    content_sha: str = ""
    status: SkillStatus = SkillStatus.DRAFT
    held_out_score: float | None = None
    token_estimate: int = 0
    provenance: list[str] = Field(default_factory=list)
    rationale: str = ""
    # Skill registry v2 (Alpha 21 WS2): richer applicability + audit history.
    applicability: dict[str, str] = Field(default_factory=dict)  # extra match conditions
    risk_class: str = "low"                  # low | medium | high (gates risky scopes)
    required_tools: list[str] = Field(default_factory=list)
    allowed_repositories: list[str] = Field(default_factory=list)  # [] == any
    validation_history: list[float] = Field(default_factory=list)  # held-out scores over time
    negative_transfer_history: list[str] = Field(default_factory=list)  # scopes it hurt
    deployment_state: str = "registered"     # registered | canary | active | retired
    rollback_pointer: str | None = None      # the version to roll back to
    skill_family: str = ""                    # family for cross-version capability rollups

    def model_post_init(self, __context: object) -> None:  # noqa: D401
        # Keep the content hash + a cheap token estimate in sync with content.
        object.__setattr__(self, "content_sha", content_hash(self.content))
        object.__setattr__(self, "token_estimate", max(1, len(self.content) // 4)
                           if self.content else 0)
        if not self.skill_family:
            object.__setattr__(self, "skill_family", self.name)
