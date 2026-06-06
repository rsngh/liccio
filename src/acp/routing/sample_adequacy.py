"""Sample-adequacy: which capability cells are statistically robust (Alpha 25+ item 4).

The honest caveat is that capability/uplift numbers are "directionally valid but small-
sample." This module makes that distinction MEASURABLE: for each cell it computes the Wilson
CI width on the conclusive solve rate and classifies the cell as ROBUST (enough samples for
a tight interval), DIRECTIONAL (a real but wide estimate), or INSUFFICIENT (too few to trust
at all). A matrix-level summary reports how much of the evidence base is robust — so "grow
the samples" has a target and a finish line, not a vibe.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.routing.cell_statistics import wilson_interval

# A cell is robust when its conclusive-solve-rate CI is at least this tight AND it has at
# least this many conclusive samples; directional when it has signal but a wide interval.
ROBUST_MAX_CI_WIDTH = 0.25
ROBUST_MIN_N = 20
DIRECTIONAL_MIN_N = 5


@dataclass
class CellAdequacy:
    cell_key: str
    n_conclusive: int
    solve_rate: float
    ci_low: float
    ci_high: float
    ci_width: float
    tier: str                  # robust | directional | insufficient

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def cell_adequacy(*, cell_key: str, successes: int, n_conclusive: int) -> CellAdequacy:
    iv = wilson_interval(successes, n_conclusive)
    width = round(iv.high - iv.low, 4)
    if n_conclusive >= ROBUST_MIN_N and width <= ROBUST_MAX_CI_WIDTH:
        tier = "robust"
    elif n_conclusive >= DIRECTIONAL_MIN_N:
        tier = "directional"
    else:
        tier = "insufficient"
    return CellAdequacy(cell_key=cell_key, n_conclusive=n_conclusive,
                        solve_rate=round(iv.point, 4), ci_low=round(iv.low, 4),
                        ci_high=round(iv.high, 4), ci_width=width, tier=tier)


def matrix_adequacy(cells: list) -> dict:
    """Summarize sample adequacy across capability-matrix cell dicts.

    Each cell dict carries ``success_rate`` and a conclusive sample size; cells with no
    conclusive samples are ignored (they carry no task signal to assess).
    """
    rows: list[dict] = []
    for c in cells:
        n = int(c.get("conclusive_sample_size") or c.get("sample_size") or 0)
        if n <= 0:
            continue
        key = c.get("agent_class", "?") + "/" + c.get("task_type", "?") + "/" + \
            c.get("risk_level", "?")
        rows.append(cell_adequacy(cell_key=key, successes=round(c.get("success_rate", 0) * n),
                                  n_conclusive=n).to_dict())
    from collections import Counter
    tiers = Counter(r["tier"] for r in rows)
    n = len(rows) or 1
    return {"n_cells": len(rows), "by_tier": dict(tiers),
            "robust_fraction": round(tiers.get("robust", 0) / n, 4),
            "mean_ci_width": round(sum(r["ci_width"] for r in rows) / n, 4),
            "thresholds": {"robust_max_ci_width": ROBUST_MAX_CI_WIDTH,
                           "robust_min_n": ROBUST_MIN_N},
            "cells": sorted(rows, key=lambda r: r["ci_width"], reverse=True)}
