"""Skill evolution timeline (Round 18).

Each autonomous self-improvement cycle records what it did to each skill scope —
deployed a new version, rejected a candidate (and why), or made no change — so the
skill's evolution is a durable, auditable timeline, not an opaque background process.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class SkillEvolutionEvent(ACPModel):
    """One outcome of a self-improvement cycle for a skill scope."""

    id: str = Field(default_factory=lambda: new_id("skev"))
    created_at: datetime = Field(default_factory=utcnow)
    scope_key: str
    action: str  # deployed | rejected | no_op | rolled_back
    skill_id: str | None = None
    from_version: int | None = None
    to_version: int | None = None
    base_score: float | None = None
    best_score: float | None = None
    reason: str = ""
    cycle_id: str = ""
