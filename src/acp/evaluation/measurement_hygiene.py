"""Attempt-outcome classification + measurement-hygiene reporting (WS1).

This is the single source of truth that turns a raw attempt (its status, whether
the workspace verified, how it errored, how much tool activity it showed) into an
:class:`AttemptOutcome`. The capability matrix and OPE consume the classification
so that infrastructure noise (provider hangs, 429/500, retries) never updates a
model's solve-rate — the central lesson of the live bakeoff.

The classifier is intentionally signal-based (works off a plain dict cell or an
``AgentAttemptResult``-shaped object), so the bakeoff, the live ingest path, and
unit tests all share one rulebook.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from acp.core.enums import AttemptOutcome
from acp.schemas.measurement import AttemptOutcomeRecord, MeasurementHygieneReport

# Error-substring signatures for provider/infra failure attribution.
_TIMEOUT_SIGNS = ("timed out", "timeout")
_RATE_LIMIT_SIGNS = ("rate limit", "429", "too many requests")
_SERVER_ERR_SIGNS = ("500", "502", "503", "internal server error", "overloaded",
                     "service unavailable")
_RETRY_SIGNS = ("retries exceeded", "max retries", "retry_exceeded")

# Above this share of inconclusive/infra attempts, a solve_rate is not trustworthy.
CONTAMINATION_THRESHOLD = 0.30


def _get(cell: Any, key: str, default: Any = None) -> Any:
    if isinstance(cell, Mapping):
        return cell.get(key, default)
    return getattr(cell, key, default)


def classify_attempt(cell: Any) -> AttemptOutcome:
    """Classify one attempt cell into an :class:`AttemptOutcome`.

    Recognized signals: ``success`` (verified solve), ``status`` / ``timed_out``,
    ``error`` (provider attribution), ``tool_calls`` (activation), ``is_harness``.
    """
    success = bool(_get(cell, "success", False) or _get(cell, "verification_pass", False))
    status = str(_get(cell, "status", "") or "").lower()
    error = str(_get(cell, "error", "") or "").lower()
    tool_calls = int(_get(cell, "tool_calls", 0) or 0)
    is_harness = bool(_get(cell, "is_harness", False))
    timed_out = bool(_get(cell, "timed_out", False)) or status in ("timed_out", "timeout") \
        or any(s in error for s in _TIMEOUT_SIGNS)

    # Solved tasks are conclusive successes regardless of a *later* hang.
    if success:
        if timed_out:
            return AttemptOutcome.INFRA_TIMEOUT_AFTER_SOLUTION
        return AttemptOutcome.TASK_SUCCESS

    # Provider-attributable failures (inconclusive: infra, not model skill).
    if any(s in error for s in _RETRY_SIGNS):
        return AttemptOutcome.PROVIDER_RETRY_EXCEEDED
    if any(s in error for s in _RATE_LIMIT_SIGNS):
        return AttemptOutcome.PROVIDER_RATE_LIMIT
    if any(s in error for s in _SERVER_ERR_SIGNS):
        return AttemptOutcome.PROVIDER_SERVER_ERROR

    if timed_out:
        # No tool activity at all -> the first call hung; pure infra, no signal.
        # With tool activity but unsolved -> the agent worked but didn't finish in
        # budget: a genuine (agent-side) non-completion, conclusive.
        if tool_calls == 0:
            return AttemptOutcome.INFRA_TIMEOUT_BEFORE_ACTION
        return AttemptOutcome.TASK_FAILURE

    # A harness that never emitted a tool call failed to *activate* (distinct from
    # a model that tried and produced a wrong solution).
    if is_harness and tool_calls == 0:
        return AttemptOutcome.HARNESS_ACTIVATION_FAILURE

    return AttemptOutcome.TASK_FAILURE


def classify_record(cell: Any) -> AttemptOutcomeRecord:
    """Classify and wrap an attempt into a self-describing record."""
    outcome = classify_attempt(cell)
    return AttemptOutcomeRecord(
        attempt_id=_get(cell, "attempt_id") or _get(cell, "task"),
        adapter_name=str(_get(cell, "adapter", "unknown") or "unknown"),
        model_name=_get(cell, "model_name"),
        task_type=str(_get(cell, "task_type", "unknown") or "unknown"),
        outcome=outcome,
        is_conclusive_quality=outcome.is_conclusive_quality,
        is_success=outcome.is_success,
        is_infra=outcome.is_infra,
        reason=(_get(cell, "error") or None),
        tool_calls=int(_get(cell, "tool_calls", 0) or 0),
        latency_s=float(_get(cell, "latency_s", 0.0) or 0.0),
        cost_usd=float(_get(cell, "cost_usd", 0.0) or 0.0),
    )


def build_hygiene_report(cells: list[Any]) -> MeasurementHygieneReport:
    """Roll a list of attempt cells into a :class:`MeasurementHygieneReport`.

    ``solve_rate`` uses conclusive attempts only; if too large a share of attempts
    are inconclusive/infra the report is flagged ``contaminated`` so callers do not
    trust the solve_rate at face value.
    """
    records = [classify_record(c) for c in cells]
    n = len(records)
    conclusive = [r for r in records if r.is_conclusive_quality]
    successes = [r for r in conclusive if r.is_success]
    infra = [r for r in records if r.is_infra and not r.is_success]
    inconclusive = [r for r in records
                    if not r.is_conclusive_quality and not r.is_infra]
    n_inconclusive_total = n - len(conclusive)
    by_outcome = Counter(str(getattr(r.outcome, "value", r.outcome)) for r in records)
    contamination_reasons: list[str] = []
    inconclusive_rate = (n_inconclusive_total / n) if n else 0.0
    if n and inconclusive_rate > CONTAMINATION_THRESHOLD:
        contamination_reasons.append(
            f"{n_inconclusive_total}/{n} attempts inconclusive/infra "
            f"({inconclusive_rate:.0%} > {CONTAMINATION_THRESHOLD:.0%})")
    if not conclusive and n:
        contamination_reasons.append("no conclusive attempts")
    return MeasurementHygieneReport(
        n_attempts=n,
        n_conclusive=len(conclusive),
        n_success=len(successes),
        n_infra=len(infra),
        n_inconclusive=len(inconclusive),
        solve_rate=round(len(successes) / len(conclusive), 4) if conclusive else 0.0,
        conclusive_rate=round(len(conclusive) / n, 4) if n else 0.0,
        infra_failure_rate=round(len(infra) / n, 4) if n else 0.0,
        inconclusive_rate=round(inconclusive_rate, 4),
        by_outcome=dict(by_outcome),
        contaminated=bool(contamination_reasons),
        contamination_reasons=contamination_reasons,
    )
