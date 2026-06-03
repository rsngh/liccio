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
