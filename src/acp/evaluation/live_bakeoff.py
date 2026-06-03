"""Live-bakeoff result assembly (Alpha 11, WS14).

The live bakeoff script (`evals/scripts/run_live_bakeoff.py`) runs real harnesses
on real no-patch tasks and produces per-(task, adapter) *observed* cells. This
module turns those observed cells into a real capability matrix and a real OPE log
— the same data structures the synthetic generators produce, but sourced from
actual agent behavior. Kept here (not just in the script) so the assembly is unit
tested without needing API keys.
"""

from __future__ import annotations

from typing import Any


def assemble_capability_matrix(cells: list[dict[str, Any]]):
    """Build a CapabilityMatrix from observed bakeoff cells."""
    from acp.routing.capability_matrix import CapabilityMatrix

    return CapabilityMatrix.from_bakeoff_report({"cells": cells})


def assemble_ope(cells: list[dict[str, Any]]) -> dict:
    """Build a real OPE report from observed cells (adapter = action, solved = reward)."""
    from acp.routing.ope import OPESample, evaluate_policy, fit_reward_model

    by_task: dict[str, list[dict]] = {}
    for c in cells:
        by_task.setdefault(c.get("task_type", "unknown"), []).append(c)
    samples: list[OPESample] = []
    for ttype, group in by_task.items():
        actions = sorted({c["adapter"] for c in group})
        for c in group:
            samples.append(OPESample(ttype, c["adapter"], 1.0 / len(actions),
                                     1.0 if c.get("success") else 0.0, actions))
    if not samples:
        return {"n": 0, "source": "REAL observed agent runs"}
    q = fit_reward_model(samples)

    def greedy(ctx: str, action: str, cands: list[str]) -> float:
        best = max(q(ctx, a) for a in cands)
        winners = [a for a in cands if q(ctx, a) == best]
        return 1.0 / len(winners) if action in winners else 0.0

    def random_t(ctx: str, action: str, cands: list[str]) -> float:
        return 1.0 / len(cands)

    baseline = sum(s.reward for s in samples) / len(samples)
    return {
        "n": len(samples), "source": "REAL observed agent runs",
        "logged_mean_reward": round(baseline, 4),
        "greedy_dr": evaluate_policy(samples, greedy, seed=1).dr.as_dict(),
        "random_dr": evaluate_policy(samples, random_t, seed=1).dr.as_dict(),
        "best_adapter_per_task_type": {
            tt: max({c["adapter"] for c in g},
                    key=lambda a: sum(c["success"] for c in g if c["adapter"] == a))
            for tt, g in by_task.items()},
    }


def solved_by_adapter(cells: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cells:
        out[c["adapter"]] = out.get(c["adapter"], 0) + int(bool(c.get("success")))
    return out
