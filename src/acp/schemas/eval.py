"""Evaluation report entities (round-2 Block F).

Eval runs (context benchmark, bakeoff, soak, bandit) become durable product data
— queryable, replayable, and feedable into router training — not just JSON files.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from acp.core.ids import new_id
from acp.core.time import utcnow
from acp.schemas.base import ACPModel


class EvalRun(ACPModel):
    id: str = Field(default_factory=lambda: new_id("evalrun"))
    kind: str  # context_benchmark | bakeoff | soak | bandit_monte_carlo
    status: str = "completed"
    summary: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalCase(ACPModel):
    id: str = Field(default_factory=lambda: new_id("evalcase"))
    eval_run_id: str
    name: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"


class EvalMetric(ACPModel):
    id: str = Field(default_factory=lambda: new_id("evalmetric"))
    eval_run_id: str
    name: str
    value: float
    unit: str = ""


class EvalReport(ACPModel):
    id: str = Field(default_factory=lambda: new_id("evalreport"))
    eval_run_id: str
    fmt: str = "json"  # json | markdown
    content: dict[str, Any] = Field(default_factory=dict)
    markdown: str = ""
    created_at: datetime = Field(default_factory=utcnow)
