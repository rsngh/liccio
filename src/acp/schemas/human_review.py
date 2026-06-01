"""Human review queue schemas (charter §7.3, §15.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.enums import HumanVerdict
from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class HumanReviewItem(ACPModel):
    id: str = Field(default_factory=lambda: new_id("review"))
    task_id: str
    attempt_id: str | None = None
    run_id: str | None = None
    reason: str
    priority: float = 0.0
    status: str = "open"  # open | resolved
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HumanLabel(ACPModel):
    id: str = Field(default_factory=lambda: new_id("label"))
    review_item_id: str
    task_id: str
    attempt_id: str | None = None
    verdict: HumanVerdict
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    reviewer: str = "anonymous"
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
