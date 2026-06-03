"""Report warehouse entities (Alpha 11, WS18).

Reports are currently files validated by the manifest. The warehouse makes every
report a *queryable* entity with a hash, summary metrics, and lineage, so an
operator can list reports, show one, and diff a report's metrics across two
ingests over time — not just read JSON off disk.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class ReportMetric(ACPModel):
    name: str
    value: float


class Report(ACPModel):
    id: str = Field(default_factory=lambda: new_id("report"))
    path: str
    kind: str  # the report's schema kind (its path)
    hash: str
    valid: bool = True
    size_bytes: int = 0
    metrics: list[ReportMetric] = Field(default_factory=list)
    ingest_id: str = ""  # groups all reports from one `acp reports ingest`
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def metric_map(self) -> dict[str, float]:
        return {m.name: m.value for m in self.metrics}


class ReportLineage(ACPModel):
    id: str = Field(default_factory=lambda: new_id("lineage"))
    report_id: str
    source_command: str = ""
    parent_ingest_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
