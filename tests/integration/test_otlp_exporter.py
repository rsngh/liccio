"""OTLP span exporter integration test (charter §23.3, Alpha-6 WS7).

Verifies that exporting N ACP SpanRecords yields N OTel spans with matching
names/attributes, using an in-memory OTel collector (no network endpoint).
"""

from __future__ import annotations

import pytest

from acp.observability.otlp import OTLPSpanExporter
from acp.schemas.trace import SpanRecord

pytestmark = pytest.mark.live_otlp

otel = pytest.importorskip(
    "opentelemetry.sdk.trace.export.in_memory_span_exporter",
    reason="opentelemetry SDK not installed",
)


def test_available_is_bool() -> None:
    # Graceful-unavailable contract: available() never raises and returns a bool.
    assert isinstance(OTLPSpanExporter.available(), bool)


def test_inert_without_exporter() -> None:
    # No injected OTel exporter -> nothing exported, no raise.
    exporter = OTLPSpanExporter()
    assert exporter.export([SpanRecord(trace_id="t1", name="acp.workflow")]) == 0


def test_exports_spans_to_in_memory_collector() -> None:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    collector = InMemorySpanExporter()
    exporter = OTLPSpanExporter(otel_exporter=collector)

    records = [
        SpanRecord(
            trace_id="trace-1",
            name="acp.classify_task",
            attributes={"task_kind": "bugfix", "n": 3},
            status="ok",
            duration_ms=12.5,
        ),
        SpanRecord(
            trace_id="trace-1",
            name="acp.verify",
            attributes={"passed": True},
            status="error",
            duration_ms=4.0,
        ),
    ]

    exported = exporter.export(records)
    assert exported == 2

    finished = collector.get_finished_spans()
    assert len(finished) == 2

    by_name = {s.name: s for s in finished}
    assert set(by_name) == {"acp.classify_task", "acp.verify"}

    classify = by_name["acp.classify_task"]
    assert classify.attributes["acp.trace_id"] == "trace-1"
    assert classify.attributes["acp.status"] == "ok"
    assert classify.attributes["acp.duration_ms"] == 12.5
    assert classify.attributes["acp.attr.task_kind"] == "bugfix"
    assert classify.attributes["acp.attr.n"] == 3

    verify = by_name["acp.verify"]
    assert verify.attributes["acp.status"] == "error"
    assert verify.attributes["acp.attr.passed"] is True
