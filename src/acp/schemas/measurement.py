"""Measurement-hygiene schemas (Alpha 11/12 WS1).

These make "is this measurement trustworthy?" a first-class, persisted concern.
An :class:`AttemptOutcomeRecord` is the classified result of one agent attempt;
a :class:`MeasurementHygieneReport` rolls many up into conclusive-vs-infra rates
so the capability matrix and OPE can consume only trustworthy task signal.
"""

from __future__ import annotations

from pydantic import Field

from acp.core.enums import AttemptOutcome
from acp.core.ids import new_id
from acp.schemas.base import ACPModel


class AttemptOutcomeRecord(ACPModel):
    """One attempt, classified into a conclusive/infra/inconclusive outcome.

    ``is_conclusive_quality`` / ``is_success`` / ``is_infra`` are denormalized
    from ``outcome`` so persisted rows and reports are self-describing without
    re-deriving the enum semantics. Persisted as a durable evidence row (WS8).
    """

    id: str = Field(default_factory=lambda: new_id("aor"))
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
    # WS2 learning-gate fields: explicit eligibility so no input layer re-derives
    # the rules. A sample may update a QUALITY metric (solve-rate) only when
    # ``include_in_quality_denominator``; it updates RELIABILITY otherwise.
    conclusive: bool = False
    contaminated: bool = False
    infra_failure_kind: str | None = None     # which infra mode, if any
    provider_failure_kind: str | None = None  # rate_limit | server_error | retry_exceeded
    verification_valid: bool = False          # a verification verdict was obtained
    tool_activation_valid: bool = True        # harness emitted >=1 tool call (or n/a)
    harness_adherence_valid: bool = False     # read+write+verify pattern followed
    cost_billable: bool = False               # the attempt incurred provider cost
    include_in_quality_denominator: bool = False
    include_in_reliability_denominator: bool = True


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
