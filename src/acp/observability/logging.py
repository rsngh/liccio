"""Structured JSON logging via structlog, with secret redaction.

A processor runs redaction over every event dict so secrets never reach stdout
or log files. ``configure_logging`` is idempotent.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog

from acp.core.redaction import Redactor

_configured = False


def _redaction_processor(redactor: Redactor):
    def processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return {
            k: (Redactor().redact(v) if not redactor.key_is_sensitive(str(k)) else "***REDACTED***")
            for k, v in event_dict.items()
        }

    return processor


def configure_logging(
    level: str = "INFO",
    json_logs: bool = True,
    redactor: Redactor | None = None,
) -> None:
    """Configure structlog. Safe to call multiple times."""
    global _configured
    redactor = redactor or Redactor()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redaction_processor(redactor),
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level) if isinstance(level, str) else level
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "acp", **initial: Any) -> structlog.stdlib.BoundLogger:
    if not _configured:
        configure_logging()
    return structlog.get_logger(name).bind(**initial)
