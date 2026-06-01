"""Budget ledger + hard-stop enforcement for harness loops (round-5 WS12).

A true harness drives an open-ended tool loop against a paid model; without hard
limits a single run can burn unbounded cost, wall-time, steps, or tool calls and
write an unbounded trace. ``BudgetLedger`` makes every loop accountable:

* ``BudgetPolicy`` declares the caps (cost / wall / steps / tool calls).
* ``BudgetLedger`` accumulates spend and, before each step, returns a structured
  violation reason the harness uses to stop *cleanly* (bounded trace, recorded
  failure) rather than running away.
* ``BudgetEvent`` records each charge + the terminal violation for provenance;
  the harness surfaces them and the service persists them as audit events.

This is pure and dependency-free so it is trivially testable without an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.schemas.base import ACPModel


@dataclass
class BudgetPolicy:
    max_cost_usd: float = 5.0
    max_wall_time_s: float = 600.0
    max_steps: int = 8
    max_tool_calls: int = 50


class BudgetEvent(ACPModel):
    kind: str                # "charge" | "violation"
    resource: str            # "cost" | "wall" | "steps" | "tool_calls"
    amount: float = 0.0
    cumulative: float = 0.0
    limit: float = 0.0
    exceeded: bool = False
    attempt_id: str | None = None


@dataclass
class BudgetLedger:
    """Accumulates a single harness run's spend against a :class:`BudgetPolicy`.

    Time is injected (``clock``) so tests are deterministic; the default uses a
    monotonic clock. ``violation(now)`` is the single hard-stop decision point.
    """

    policy: BudgetPolicy
    started_at: float = 0.0
    cost_usd: float = 0.0
    steps: int = 0
    tool_calls: int = 0
    events: list[BudgetEvent] = field(default_factory=list)
    attempt_id: str | None = None

    def start(self, now: float) -> None:
        self.started_at = now

    def charge_cost(self, amount: float) -> None:
        self.cost_usd += max(0.0, amount)
        self.events.append(BudgetEvent(
            kind="charge", resource="cost", amount=amount, cumulative=self.cost_usd,
            limit=self.policy.max_cost_usd, exceeded=self.cost_usd > self.policy.max_cost_usd,
            attempt_id=self.attempt_id))

    def add_tool_calls(self, n: int) -> None:
        self.tool_calls += n

    def begin_step(self) -> None:
        self.steps += 1

    def _violate(self, resource: str, cumulative: float, limit: float) -> str:
        self.events.append(BudgetEvent(
            kind="violation", resource=resource, cumulative=cumulative, limit=limit,
            exceeded=True, attempt_id=self.attempt_id))
        return f"budget_exceeded:{resource}"

    def violation(self, now: float) -> str | None:
        """Return a structured stop reason if any cap is exceeded, else None."""
        if now - self.started_at > self.policy.max_wall_time_s:
            return self._violate("wall", now - self.started_at, self.policy.max_wall_time_s)
        if self.cost_usd > self.policy.max_cost_usd:
            return self._violate("cost", self.cost_usd, self.policy.max_cost_usd)
        if self.steps > self.policy.max_steps:
            return self._violate("steps", self.steps, self.policy.max_steps)
        if self.tool_calls > self.policy.max_tool_calls:
            return self._violate("tool_calls", self.tool_calls, self.policy.max_tool_calls)
        return None

    def summary(self) -> dict:
        return {"cost_usd": round(self.cost_usd, 6), "steps": self.steps,
                "tool_calls": self.tool_calls,
                "violations": [e.resource for e in self.events if e.kind == "violation"]}
