"""Measurement-hygiene schemas (Alpha 11/12 WS1).

These make "is this measurement trustworthy?" a first-class, persisted concern.
An :class:`AttemptOutcomeRecord` is the classified result of one agent attempt;
a :class:`MeasurementHygieneReport` rolls many up into conclusive-vs-infra rates
so the capability matrix and OPE can consume only trustworthy task signal.
"""

from __future__ import annotations

from pydantic import Field

from acp.core.enums import AttemptOutcome
from acp.schemas.base import ACPModel


class AttemptOutcomeRecord(ACPModel):
    """One attempt, classified into a conclusive/infra/inconclusive outcome.

    ``is_conclusive_quality`` / ``is_success`` / ``is_infra`` are denormalized
    from ``outcome`` so persisted rows and reports are self-describing without
    re-deriving the enum semantics.
    """

    attempt_id: str | None = None
    adapter_name: str = "unknown"
    model_name: str | None = None
    task_type: str = "unknown"
    outcome: AttemptOutcome
    is_conclusive_quality: bool = False
    is_success: bool = False
    is_infra: bool = False
    reason: str | None = None
    tool_calls: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0


class MeasurementHygieneReport(ACPModel):
    """Rolled-up measurement quality over a set of attempts.

    ``solve_rate`` is computed over *conclusive* attempts only (the no-poisoning
    guarantee); ``infra_failure_rate`` / ``inconclusive_rate`` track the rest so a
    reviewer can see whether a conclusion rests on clean task outcomes.
    """

    n_attempts: int = 0
    n_conclusive: int = 0
    n_success: int = 0
    n_infra: int = 0
    n_inconclusive: int = 0
    solve_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    conclusive_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    infra_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    inconclusive_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    by_outcome: dict[str, int] = Field(default_factory=dict)
    # True when measurement quality is too poor to trust the solve_rate.
    contaminated: bool = False
    contamination_reasons: list[str] = Field(default_factory=list)
