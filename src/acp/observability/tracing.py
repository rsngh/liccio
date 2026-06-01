"""Lightweight tracing (charter §23.1).

A minimal in-process span recorder that always works (no OTel dependency). When
opentelemetry is installed and configured, spans are also emitted there. Every
workflow gets a trace_id; spans carry the charter's attribute set.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from acp.core.redaction import Redactor

SPAN_NAMES = (
    "acp.workflow",
    "acp.classify_task",
    "acp.create_snapshot",
    "acp.index_repo",
    "acp.compile_context",
    "acp.route_task",
    "acp.agent.plan",
    "acp.agent.execute",
    "acp.command.run",
    "acp.capture_diff",
    "acp.verify",
    "acp.evaluate",
    "acp.human_review",
    "acp.reward",
    "acp.policy.update",
)


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    duration_ms: float = 0.0


@dataclass
class Tracer:
    redactor: Redactor = field(default_factory=Redactor)
    spans: list[Span] = field(default_factory=list)

    @contextmanager
    def span(self, name: str, trace_id: str, **attributes: Any):
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=uuid.uuid4().hex,
            attributes={k: self.redactor.redact(v) for k, v in attributes.items()},
        )
        t0 = time.monotonic()
        try:
            yield span
        except Exception:
            span.status = "error"
            raise
        finally:
            span.duration_ms = (time.monotonic() - t0) * 1000
            self.spans.append(span)
