"""Observability export hardening (charter §23.3, Alpha-8 WS16).

Export commands for traces and eval data in multiple formats, with explicit,
honest health states for optional exporters. The always-available paths (JSONL
traces, JSON eval) never depend on optional packages; optional paths (OTLP,
parquet, and the third-party sinks Braintrust/LangSmith/Phoenix) degrade
gracefully — they report an ``unavailable`` health state and never raise on a
missing dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acp.core.optional import try_import
from acp.observability.otlp import OTLPSpanExporter
from acp.schemas.trace import SpanRecord


def export_traces(
    spans: list[SpanRecord],
    *,
    fmt: str,
    out: str,
    otlp_exporter: OTLPSpanExporter | None = None,
) -> dict[str, Any]:
    """Export SpanRecords as ``jsonl`` or ``otlp``.

    ``jsonl`` writes one JSON object per span to ``out`` and always works.
    ``otlp`` ships spans through an injected :class:`OTLPSpanExporter`; when no
    exporter is supplied or the OTel SDK is absent it is inert and reports
    ``exported=0`` with a clear health state. Returns
    ``{format, exported, health}``.
    """
    if fmt == "jsonl":
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for span in spans:
                fh.write(json.dumps(span.model_dump(mode="json"), default=str) + "\n")
        return {"format": "jsonl", "exported": len(spans), "health": "ok"}

    if fmt == "otlp":
        if otlp_exporter is None:
            return {
                "format": "otlp",
                "exported": 0,
                "health": "inert: no OTLP exporter injected",
            }
        if not OTLPSpanExporter.available():
            return {
                "format": "otlp",
                "exported": 0,
                "health": "unavailable: opentelemetry SDK not installed",
            }
        exported = otlp_exporter.export(spans)
        return {"format": "otlp", "exported": exported, "health": "ok"}

    raise ValueError(f"unsupported trace export format: {fmt!r} (expected jsonl|otlp)")


def export_eval(rows: list[dict[str, Any]], *, fmt: str, out: str) -> dict[str, Any]:
    """Export eval rows as ``json`` or ``parquet``.

    ``json`` writes a JSON array to ``out`` and always works. ``parquet`` uses
    pyarrow via :func:`try_import`; when pyarrow is unavailable it writes nothing
    and reports an ``unavailable`` health state (no crash). Returns
    ``{format, written, health}``.
    """
    if fmt == "json":
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
        return {"format": "json", "written": len(rows), "health": "ok"}

    if fmt == "parquet":
        pa = try_import("pyarrow")
        pq = try_import("pyarrow.parquet")
        if pa is None or pq is None:
            return {
                "format": "parquet",
                "written": 0,
                "health": "unavailable: pyarrow not installed",
            }
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Stringify nested values so heterogeneous dict columns serialize cleanly.
        normalized = [
            {k: (v if isinstance(v, (str, int, float, bool)) else json.dumps(v, default=str))
             for k, v in row.items()}
            for row in rows
        ]
        table = pa.Table.from_pylist(normalized)
        pq.write_table(table, str(path))
        return {"format": "parquet", "written": len(rows), "health": "ok"}

    raise ValueError(f"unsupported eval export format: {fmt!r} (expected json|parquet)")


def optional_exporter_health() -> dict[str, dict[str, Any]]:
    """Honest health for each optional observability sink.

    Each entry is ``{available: bool, detail: str}``, probed via
    :func:`try_import` (or :meth:`OTLPSpanExporter.available`). Never raises;
    in this environment all optional sinks are expected to be unavailable.
    """

    def _probe(name: str, module: str) -> dict[str, Any]:
        ok = try_import(module) is not None
        return {
            "available": ok,
            "detail": "ready" if ok else f"unavailable: {name} ({module}) not installed",
        }

    otlp_ok = OTLPSpanExporter.available()
    return {
        "braintrust": _probe("braintrust", "braintrust"),
        "langsmith": _probe("langsmith", "langsmith"),
        "phoenix": _probe("phoenix", "phoenix"),
        "otlp": {
            "available": otlp_ok,
            "detail": "ready" if otlp_ok else "unavailable: opentelemetry SDK not installed",
        },
        "parquet": _probe("parquet", "pyarrow"),
    }
