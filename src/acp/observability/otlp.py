"""Real OpenTelemetry span exporter for ACP traces (charter §23.3).

Optional integration: the in-process JSONLExporter always works. When the
``opentelemetry`` SDK is installed, this wrapper converts ACP SpanRecords into
OTel spans and ships them through any OTel span exporter (a real OTLP exporter
in production, or an InMemorySpanExporter in tests). It reports ``available``
False — never raises on import — when the SDK is absent.
"""

from __future__ import annotations

from typing import Any

from acp.schemas.trace import SpanRecord


class OTLPSpanExporter:
    """ACP-side wrapper that exports SpanRecords via an OTel span exporter.

    A concrete OTel exporter (e.g. ``OTLPSpanExporter`` from
    ``opentelemetry.exporter.otlp`` or an ``InMemorySpanExporter``) is injected
    so the same code serves production and tests. When no exporter is supplied
    and the SDK is unavailable, the wrapper is inert.
    """

    def __init__(
        self,
        otel_exporter: Any | None = None,
        service_name: str = "acp",
    ) -> None:
        self._otel_exporter = otel_exporter
        self.service_name = service_name

    @staticmethod
    def available() -> bool:
        """True when the opentelemetry SDK can be imported."""
        from acp.core.optional import try_import

        return (
            try_import("opentelemetry.sdk.trace") is not None
            and try_import("opentelemetry.sdk.trace.export") is not None
        )

    def export(self, spans: list[SpanRecord]) -> int:
        """Convert SpanRecords to OTel spans and export them.

        Returns the number of spans exported (0 if unavailable / inert).
        """
        if self._otel_exporter is None or not self.available():
            return 0

        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": self.service_name})
        )
        provider.add_span_processor(SimpleSpanProcessor(self._otel_exporter))
        tracer = provider.get_tracer("acp")

        count = 0
        for record in spans:
            otel_span = tracer.start_span(record.name)
            otel_span.set_attribute("acp.trace_id", record.trace_id)
            otel_span.set_attribute("acp.span_id", record.id)
            otel_span.set_attribute("acp.status", record.status)
            otel_span.set_attribute("acp.duration_ms", record.duration_ms)
            for key, value in record.attributes.items():
                otel_span.set_attribute(f"acp.attr.{key}", _coerce(value))
            otel_span.end()
            count += 1

        provider.force_flush()
        return count


def _coerce(value: Any) -> Any:
    """OTel attributes accept str/bool/int/float (and sequences); stringify the rest."""
    if isinstance(value, (str, bool, int, float)):
        return value
    return str(value)
