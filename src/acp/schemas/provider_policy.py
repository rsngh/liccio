"""Provider call policy (Alpha 11/12 WS2).

Declares the budget-safety contract every provider-backed harness must honor, so
the live-bakeoff failure (provider SDK default retries blew a 120s budget to 607s)
can never recur silently. The policy is a declared, introspectable value — tests
assert harness clients are constructed to match it.
"""

from __future__ import annotations

from acp.schemas.base import ACPModel


class ProviderPolicy(ACPModel):
    """Per-provider call governance.

    - ``max_retries`` 0 by default: the harness drives its own multi-step loop, so
      SDK-internal retries (which multiply wall time on a timeout) are disabled.
    - ``per_call_timeout_s``: hard ceiling on a single request, also bounded by the
      remaining wall budget at call time.
    - ``retry_non_timeout_only``: our own bounded retries cover transient 429/5xx but
      never a timeout (a timeout retry would redo work / blow the budget).
    """

    provider: str
    max_retries: int = 0
    per_call_timeout_s: float = 60.0
    retry_non_timeout_only: bool = True
    wall_budget_enforced: bool = True

    def is_budget_safe(self) -> bool:
        """True iff this policy cannot silently violate the wall-time budget."""
        return (self.max_retries == 0 and self.per_call_timeout_s > 0
                and self.wall_budget_enforced)


class ProviderCallRecord(ACPModel):
    """An audit record of one provider API call (WS6): how many retries the SDK
    used, how long it took, whether it timed out, and how an error was classified —
    so SDK behavior that exceeds the policy is observable, not silent."""

    provider: str
    model: str | None = None
    retries_used: int = 0
    wall_time_s: float = 0.0
    timed_out: bool = False
    error_kind: str | None = None  # rate_limit | server_error | timeout | retry_exceeded


class ProviderViolation(ACPModel):
    """A policy violation detected on a provider call."""

    kind: str   # retry_violation | timeout_violation
    detail: str


def detect_violations(
    record: ProviderCallRecord, policy: ProviderPolicy,
    *, wall_budget_s: float | None = None,
) -> list[ProviderViolation]:
    """Flag any way the call exceeded the policy/budget (WS6 enforcement audit)."""
    out: list[ProviderViolation] = []
    if record.retries_used > policy.max_retries:
        out.append(ProviderViolation(
            kind="retry_violation",
            detail=f"{record.retries_used} retries > policy max {policy.max_retries}"))
    cap = wall_budget_s if wall_budget_s is not None else policy.per_call_timeout_s
    if record.wall_time_s > cap + 1e-6:
        out.append(ProviderViolation(
            kind="timeout_violation",
            detail=f"wall {record.wall_time_s:.1f}s > cap {cap:.1f}s"))
    return out
