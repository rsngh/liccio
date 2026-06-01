"""Trace / span and artifact-ref schemas (charter §7.3, §23)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class ArtifactRef(ACPModel):
    """Reference to a stored artifact blob."""

    id: str = Field(default_factory=lambda: new_id("art"))
    uri: str
    content_type: str = "application/octet-stream"
    size_bytes: int = 0
    sha256: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpanRecord(ACPModel):
    id: str = Field(default_factory=lambda: new_id("span"))
    trace_id: str
    name: str
    parent_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    duration_ms: float = 0.0


class AuditEvent(ACPModel):
    id: str = Field(default_factory=lambda: new_id("audit"))
    trace_id: str | None = None
    actor: str = "system"
    event_type: str
    target: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
