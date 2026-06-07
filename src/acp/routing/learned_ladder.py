# ruff: noqa: E501
"""Offline-learned escalation ladder (AutoTTS 2605.08083 — controller search over traces).

The hand-tuned `LEVERS` priors are a guess. AutoTTS reframes test-time scaling as *searching a
controller over pre-collected traces*. Here: from logged `(failure_signature, lever, solved, cost)`
records, learn — per signature — the lever order that minimizes EXPECTED cost-to-verified-success, so
the router starts at the historically-best rung instead of escalating from scratch every time. Unlike
online memory (which warms up per deployment), this is batch-learned and fixed/auditable at deploy.

Deterministic, dependency-free.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Trace:
    failure_signature: str
    lever: str
    solved: bool
    cost: float


@dataclass
class LearnedLadder:
    per_signature: dict[str, list[str]] = field(default_factory=dict)
    fallback: list[str] = field(default_factory=list)   # global cheapest-first order
    stats: dict = field(default_factory=dict)

    def ladder_for(self, failure_signature: str) -> list[str]:
        return self.per_signature.get(failure_signature) or self.fallback


def learn_ladder(traces: list[Trace], *, fallback_order: list[str], eps: float = 1e-3) -> LearnedLadder:
    """Learn a per-signature lever order minimizing expected cost-per-success from logged traces.

    Per (signature, lever): p = solve-rate, c = mean cost. Keep levers that ever solved; order them
    by c / p ascending (cheapest expected cost per marginal success — the greedy escalation that
    minimizes expected spend). Signatures with no solving lever fall back to the global order.
    """
    agg: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])  # [n, solves, cost]
    for t in traces:
        a = agg[(t.failure_signature, t.lever)]
        a[0] += 1
        a[1] += 1.0 if t.solved else 0.0
        a[2] += t.cost
    by_sig: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for (sig, lever), (n, solves, cost) in agg.items():
        p = solves / n if n else 0.0
        c = cost / n if n else 0.0
        by_sig[sig].append((lever, p, c))
    per_sig: dict[str, list[str]] = {}
    stats: dict[str, list[dict]] = {}
    for sig, rows in by_sig.items():
        solving = [(lever, p, c) for lever, p, c in rows if p > 0]
        if not solving:
            continue
        ordered = sorted(solving, key=lambda r: (r[2] / max(r[1], eps), r[2]))
        per_sig[sig] = [lever for lever, _p, _c in ordered]
        stats[sig] = [{"lever": lever, "p_solve": round(p, 3), "mean_cost": round(c, 6)}
                      for lever, p, c in sorted(rows, key=lambda r: r[2])]
    return LearnedLadder(per_signature=per_sig, fallback=list(fallback_order), stats=stats)
