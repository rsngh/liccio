"""Context-strategy OPE (GOALS Alpha 42 P4).

Learns, from observed conclusive cells, which context strategy (none / grep / repo_map /
embedding / hybrid / …) to route per ``context_need`` bucket — by verified success per dollar,
not by assumption. Includes an honest grep-vs-embedding comparison ("Is Grep All You Need?":
grep can beat vector retrieval depending on the harness — so ACP must measure, not default to a
vector DB). Deterministic; consumes cells (e.g. from the MetaRouter Arena).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


def _get(cell: Any, key: str, default=None):
    return cell.get(key, default) if isinstance(cell, dict) else getattr(cell, key, default)


@dataclass
class StrategyEstimate:
    context_need: str
    strategy: str
    n: int
    solve_rate: float
    mean_cost: float
    value_per_dollar: float       # solve_rate / mean_cost (or solve_rate*1e6 if free)

    def to_dict(self) -> dict:
        return {"context_need": self.context_need, "strategy": self.strategy, "n": self.n,
                "solve_rate": self.solve_rate, "mean_cost": self.mean_cost,
                "value_per_dollar": self.value_per_dollar}


class ContextStrategyOPE:
    """Off-policy estimate of context-strategy value by ``context_need`` from logged cells."""

    def __init__(self, min_samples: int = 1) -> None:
        self.min_samples = min_samples
        self._cells: dict[tuple[str, str], list[tuple[bool, float]]] = defaultdict(list)

    def fit(self, cells: list[Any]) -> ContextStrategyOPE:
        for c in cells:
            if not _get(c, "conclusive", True):
                continue  # only conclusive cells inform quality (measurement trust)
            need = str(_get(c, "context_need", "unknown"))
            strat = str(_get(c, "strategy", "unknown"))
            self._cells[(need, strat)].append(
                (bool(_get(c, "solved", False)), float(_get(c, "cost_usd", 0.0) or 0.0)))
        return self

    def estimate(self, context_need: str, strategy: str) -> StrategyEstimate | None:
        rows = self._cells.get((context_need, strategy))
        if not rows:
            return None
        n = len(rows)
        solve_rate = round(sum(1 for s, _ in rows if s) / n, 4)
        mean_cost = round(sum(c for _, c in rows) / n, 6)
        vpd = round(solve_rate / mean_cost, 2) if mean_cost > 0 else round(solve_rate * 1e6, 2)
        return StrategyEstimate(context_need, strategy, n, solve_rate, mean_cost, vpd)

    def strategies_for(self, context_need: str) -> list[str]:
        return sorted({s for (need, s) in self._cells if need == context_need})

    def recommend(self, context_need: str) -> dict:
        """Best strategy for a context_need by verified success per dollar (enough samples)."""
        raw = [self.estimate(context_need, s) for s in self.strategies_for(context_need)]
        ests: list[StrategyEstimate] = [e for e in raw
                                        if e is not None and e.n >= self.min_samples]
        if not ests:
            return {"context_need": context_need, "recommended": None, "reason": "no samples"}
        # prefer highest solve rate; tie-break on value-per-dollar (cheaper wins)
        best = max(ests, key=lambda e: (e.solve_rate, e.value_per_dollar))
        return {"context_need": context_need, "recommended": best.strategy,
                "solve_rate": best.solve_rate, "value_per_dollar": best.value_per_dollar,
                "candidates": [e.to_dict() for e in sorted(ests, key=lambda x: -x.solve_rate)]}

    def grep_vs_embedding(self) -> dict:
        """Honest comparison across all buckets: does grep beat embedding/hybrid where observed?"""
        def agg(strats: set[str]) -> tuple[int, float]:
            rows = [r for (need, s), rs in self._cells.items() if s in strats for r in rs]
            if not rows:
                return 0, 0.0
            return len(rows), round(sum(1 for s, _ in rows if s) / len(rows), 4)
        n_grep, grep_rate = agg({"grep", "keyword_only"})
        n_emb, emb_rate = agg({"embedding", "embedding_only", "hybrid_keyword_embedding"})
        if not n_grep or not n_emb:
            verdict = "insufficient_evidence"
        elif grep_rate > emb_rate:
            verdict = "grep_wins"
        elif emb_rate > grep_rate:
            verdict = "embedding_wins"
        else:
            verdict = "tie"
        return {"grep_n": n_grep, "grep_solve_rate": grep_rate, "embedding_n": n_emb,
                "embedding_solve_rate": emb_rate, "verdict": verdict,
                "note": "null/insufficient results are reported honestly, not hidden"}

    def to_report(self) -> dict:
        needs = sorted({need for (need, _) in self._cells})
        return {
            "experiment": "context_strategy_ope",
            "recommendations": {n: self.recommend(n) for n in needs},
            "grep_vs_embedding": self.grep_vs_embedding(),
            "n_buckets": len(needs),
        }
