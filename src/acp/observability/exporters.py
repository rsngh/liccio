"""Span exporters (charter §23.3). Local JSONL always available; others optional."""

from __future__ import annotations

import json
from pathlib import Path

from acp.core.redaction import Redactor
from acp.observability.tracing import Span


class JSONLExporter:
    """Writes spans as one JSON object per line (secrets redacted)."""

    def __init__(self, path: Path | str, redactor: Redactor | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor or Redactor()

    def export(self, spans: list[Span]) -> int:
        with self.path.open("a", encoding="utf-8") as fh:
            for s in spans:
                record = {
                    "name": s.name,
                    "trace_id": s.trace_id,
                    "span_id": s.span_id,
                    "status": s.status,
                    "duration_ms": round(s.duration_ms, 3),
                    "attributes": self.redactor.redact(s.attributes),
                }
                fh.write(json.dumps(record, default=str) + "\n")
        return len(spans)

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
