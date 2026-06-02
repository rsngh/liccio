"""Observability export hardening tests (charter §23.3, Alpha-8 WS16)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acp.observability.export import (
    export_eval,
    export_traces,
    optional_exporter_health,
)
from acp.observability.otlp import OTLPSpanExporter
from acp.schemas.trace import SpanRecord


def _spans(n: int) -> list[SpanRecord]:
    return [
        SpanRecord(trace_id="t1", name="acp.workflow", attributes={"i": i})
        for i in range(n)
    ]


def test_jsonl_trace_export_writes_n_lines(tmp_path: Path) -> None:
    out = tmp_path / "spans.jsonl"
    result = export_traces(_spans(3), fmt="jsonl", out=str(out))
    assert result == {"format": "jsonl", "exported": 3, "health": "ok"}
    lines = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert len(lines) == 3
    assert all(line["trace_id"] == "t1" for line in lines)


def test_otlp_export_inert_without_exporter(tmp_path: Path) -> None:
    result = export_traces(_spans(2), fmt="otlp", out=str(tmp_path / "x"))
    assert result["format"] == "otlp"
    assert result["exported"] == 0
    assert "inert" in result["health"] or "unavailable" in result["health"]


def test_otlp_export_with_in_memory_exporter(tmp_path: Path) -> None:
    pytest.importorskip(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter",
        reason="opentelemetry SDK not installed",
    )
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    collector = InMemorySpanExporter()
    exporter = OTLPSpanExporter(otel_exporter=collector)
    result = export_traces(_spans(2), fmt="otlp", out=str(tmp_path / "x"), otlp_exporter=exporter)
    assert result == {"format": "otlp", "exported": 2, "health": "ok"}
    assert len(collector.get_finished_spans()) == 2


def test_unsupported_trace_format_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported trace export format"):
        export_traces(_spans(1), fmt="csv", out=str(tmp_path / "x"))


def test_eval_json_export_round_trips(tmp_path: Path) -> None:
    rows = [{"id": "r1", "score": 0.9}, {"id": "r2", "score": 0.5, "nested": {"k": 1}}]
    out = tmp_path / "eval.json"
    result = export_eval(rows, fmt="json", out=str(out))
    assert result == {"format": "json", "written": 2, "health": "ok"}
    assert json.loads(out.read_text()) == rows


def test_eval_parquet_export_graceful(tmp_path: Path) -> None:
    from acp.core.optional import try_import

    out = tmp_path / "eval.parquet"
    result = export_eval([{"id": "r1"}], fmt="parquet", out=str(out))
    assert result["format"] == "parquet"
    if try_import("pyarrow") is None:
        assert result == {
            "format": "parquet",
            "written": 0,
            "health": "unavailable: pyarrow not installed",
        }
        assert not out.exists()
    else:
        assert result["health"] == "ok"
        assert out.exists()


def test_unsupported_eval_format_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported eval export format"):
        export_eval([], fmt="xml", out=str(tmp_path / "x"))


def test_optional_exporter_health_shape() -> None:
    health = optional_exporter_health()
    assert set(health) == {"braintrust", "langsmith", "phoenix", "otlp", "parquet"}
    for name, entry in health.items():
        assert isinstance(entry["available"], bool), name
        assert isinstance(entry["detail"], str) and entry["detail"], name
