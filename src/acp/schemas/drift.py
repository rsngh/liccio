"""Persisted drift / demotion entities (Alpha 11, WS8).

Auto-demotion must be durable and inspectable, not just in-memory: a drift report,
the demotion event it triggered, and the current promotion state of each learned
model are persisted so operators can audit *why* a model was demoted and when.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class DriftReportEntity(ACPModel):
    id: str = Field(default_factory=lambda: new_id("drift"))
    model_name: str
    accuracy_drop: float = 0.0
    psi: float = 0.0
    high_risk_false_negative_rate: float = 0.0
    drifted: bool = False
    demote_recommended: bool = False
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class ModelDemotionEventEntity(ACPModel):
    id: str = Field(default_factory=lambda: new_id("demotion"))
    model_name: str
    drift_report_id: str | None = None
    reason: str = ""
    review_item_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelPromotionState(ACPModel):
    id: str = Field(default_factory=lambda: new_id("promstate"))
    model_name: str
    promoted: bool = False
    last_event: str = "init"  # init | promoted | demoted
    updated_at: datetime = Field(default_factory=utcnow)
