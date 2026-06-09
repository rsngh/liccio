# ruff: noqa: E501
"""User-facing FinOps dashboard / ledger (GOALS P5).

The evidence (heterogeneity, harness, verifier, memory rounds) now supports a product-level
FinOps story, but the existing :mod:`finops.policy_cost_report` only attributes cost *per policy*
from one arena run. The control plane's actual value proposition — "the cheapest effective lever,
which is often not the strongest model" — needs a surface that answers, across real runs:

  * cost per verified success broken down by provider / model / harness / context / topology;
  * how much was wasted on escalation rungs and extra best-of-k candidates that didn't help;
  * how much the verifier itself cost, and how much was spent on thinking/reasoning tokens;
  * whether memory is actually saving money over time (cost-per-success trend, and the delta
    versus memoryless runs);
  * the recommended default policy *per task family* — the lever the data says to start from.

:class:`FinOpsLedger` ingests one :class:`SpendRecord` per attempt and produces that
:meth:`dashboard` (a JSON-able dict) plus a compact :meth:`render_text`. Pure and
dependency-free so it is testable without any live run.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

# dimensions a verified-success cost can be sliced by (each is a SpendRecord attribute)
DIMENSIONS = ("provider", "model", "harness", "context_strategy", "topology", "policy", "task_family")


@dataclass
class SpendRecord:
    """One routed attempt's cost, dimensions, and outcome."""

    task_family: str
    provider: str = ""
    model: str = ""
    harness: str = ""
    context_strategy: str = ""
    topology: str = ""
    policy: str = ""
    solved: bool = False
    executor_cost_usd: float = 0.0
    verifier_cost_usd: float = 0.0          # the proxy/independent verifier's own cost
    thinking_cost_usd: float = 0.0          # reasoning/thinking-token spend
    wasted_escalation_cost_usd: float = 0.0  # rungs / extra candidates that did not solve it
    memory_seeded: bool = False             # did long-lived memory seed this route?
    session: int = 0                        # ordinal for "over time" trends

    @property
    def total_cost_usd(self) -> float:
        return (self.executor_cost_usd + self.verifier_cost_usd
                + self.thinking_cost_usd + self.wasted_escalation_cost_usd)


def _cost_per_verified_success(rows: list[SpendRecord]) -> float | None:
    """Total spend / number of verified successes; ``None`` when nothing succeeded (no value)."""
    solved = sum(1 for r in rows if r.solved)
    if solved == 0:
        return None
    return round(sum(r.total_cost_usd for r in rows) / solved, 6)


@dataclass
class FinOpsLedger:
    records: list[SpendRecord] = field(default_factory=list)

    def add(self, rec: SpendRecord) -> None:
        self.records.append(rec)

    # --- slices ------------------------------------------------------------------------------

    def cost_per_verified_success_by(self, dimension: str) -> dict[str, float | None]:
        """Cost per verified success grouped by one dimension (e.g. ``"model"``)."""
        if dimension not in DIMENSIONS:
            raise ValueError(f"unknown dimension {dimension!r}; pick from {DIMENSIONS}")
        groups: dict[str, list[SpendRecord]] = defaultdict(list)
        for r in self.records:
            groups[str(getattr(r, dimension)) or "(unset)"].append(r)
        return {k: _cost_per_verified_success(v) for k, v in sorted(groups.items())}

    def wasted_escalation_cost(self) -> float:
        return round(sum(r.wasted_escalation_cost_usd for r in self.records), 6)

    def verifier_cost(self) -> float:
        return round(sum(r.verifier_cost_usd for r in self.records), 6)

    def thinking_cost(self) -> float:
        return round(sum(r.thinking_cost_usd for r in self.records), 6)

    def memory_savings_over_time(self) -> dict:
        """Cost-per-verified-success per session, plus the memory-vs-memoryless delta.

        ``per_session`` shows the trend (memory should drive it down as it learns the cheap
        lever per family). ``savings_vs_memoryless`` is the absolute cost/success a memory-seeded
        route saves over a memoryless one on the same corpus (positive = memory is cheaper).
        """
        by_session: dict[int, list[SpendRecord]] = defaultdict(list)
        for r in self.records:
            by_session[r.session].append(r)
        per_session = {s: _cost_per_verified_success(rows) for s, rows in sorted(by_session.items())}
        seeded = _cost_per_verified_success([r for r in self.records if r.memory_seeded])
        memoryless = _cost_per_verified_success([r for r in self.records if not r.memory_seeded])
        savings = (round(memoryless - seeded, 6)
                   if seeded is not None and memoryless is not None else None)
        return {"per_session": per_session, "with_memory": seeded,
                "memoryless": memoryless, "savings_vs_memoryless": savings}

    def recommended_policy_by_family(self) -> dict[str, str]:
        """The lowest cost-per-verified-success policy to default to, per task family.

        A family whose policies never verify a success has no recommendation (``"(none verified)"``)
        — the honest answer, rather than recommending a policy that has never worked there.
        """
        by_family: dict[str, dict[str, list[SpendRecord]]] = defaultdict(lambda: defaultdict(list))
        for r in self.records:
            by_family[r.task_family][r.policy or "(unset)"].append(r)
        out: dict[str, str] = {}
        for family, policies in sorted(by_family.items()):
            scored = [(p, _cost_per_verified_success(rows)) for p, rows in policies.items()]
            viable = [(p, c) for p, c in scored if c is not None]
            out[family] = min(viable, key=lambda pc: pc[1])[0] if viable else "(none verified)"
        return out

    # --- the surface -------------------------------------------------------------------------

    def dashboard(self) -> dict:
        solved = sum(1 for r in self.records if r.solved)
        return {
            "n_attempts": len(self.records),
            "n_verified_success": solved,
            "total_cost_usd": round(sum(r.total_cost_usd for r in self.records), 6),
            "cost_per_verified_success": _cost_per_verified_success(self.records),
            "by_dimension": {d: self.cost_per_verified_success_by(d) for d in DIMENSIONS},
            "wasted_escalation_cost_usd": self.wasted_escalation_cost(),
            "verifier_cost_usd": self.verifier_cost(),
            "thinking_cost_usd": self.thinking_cost(),
            "memory": self.memory_savings_over_time(),
            "recommended_policy_by_family": self.recommended_policy_by_family(),
        }

    def render_text(self) -> str:
        d = self.dashboard()
        lines = [
            "FinOps dashboard",
            f"  attempts={d['n_attempts']} verified={d['n_verified_success']} "
            f"total=${d['total_cost_usd']} cost/success="
            f"{'n/a' if d['cost_per_verified_success'] is None else '$' + str(d['cost_per_verified_success'])}",
            f"  verifier=${d['verifier_cost_usd']} thinking=${d['thinking_cost_usd']} "
            f"wasted_escalation=${d['wasted_escalation_cost_usd']}",
        ]
        for dim in ("model", "harness", "context_strategy"):
            slc = d["by_dimension"][dim]
            cells = ", ".join(f"{k}={'n/a' if v is None else '$' + str(v)}" for k, v in slc.items())
            lines.append(f"  cost/success by {dim}: {cells}")
        mem = d["memory"]
        lines.append(f"  memory savings vs memoryless: "
                     f"{'n/a' if mem['savings_vs_memoryless'] is None else '$' + str(mem['savings_vs_memoryless'])}")
        for family, policy in d["recommended_policy_by_family"].items():
            lines.append(f"  recommend [{family}] -> {policy}")
        return "\n".join(lines)
