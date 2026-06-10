# ruff: noqa: E501
"""Coverage scaling — how much does each added agent buy? (informs pool size)

The boosting premise (best-of-pool = union) is established; this quantifies the *shape*: as the pool
grows 1→N agents, how fast does the union solve-rate rise, and where does it plateau? Two views, both
computed offline from the real per-agent solve vectors (easy 17 + hard 10 = combined 27):

  * greedy-best ordering — add the agent that maximizes marginal new coverage at each step (the
    optimal pool-growth curve);
  * expected random-k — average union solve-rate over all k-subsets (order-independent coverage).

Output: the curve, the per-agent marginal lift, and the "knee" (smallest pool reaching the union).

    uv run python -m evals.issue_replay.coverage_scaling --corpus combined --out reports/issue_replay_coverage_scaling.json
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

from evals.issue_replay.escalation import _load


def _union_rate(solves: dict[str, list[int]], agents: tuple[str, ...], n: int) -> float:
    return sum(1 for i in range(n) if any(solves[a][i] for a in agents)) / n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="combined", choices=["v1", "hard", "combined"])
    ap.add_argument("--out", default="reports/issue_replay_coverage_scaling.json")
    args = ap.parse_args()
    names, solves, _cost, _repos = _load(args.corpus)
    n = len(next(iter(solves.values())))
    full_union = _union_rate(solves, tuple(names), n)

    # greedy-best pool growth: at each step add the agent with the most NEW coverage
    chosen: list[str] = []
    greedy_curve = []
    remaining = set(names)
    while remaining:
        best = max(remaining, key=lambda a: _union_rate(solves, (*chosen, a), n))
        chosen.append(best)
        remaining.discard(best)
        greedy_curve.append({"k": len(chosen), "added": best,
                             "union_rate": round(_union_rate(solves, tuple(chosen), n), 3)})
    marginal = [{"k": c["k"], "added": c["added"],
                 "marginal_lift": round(c["union_rate"] - (greedy_curve[i - 1]["union_rate"] if i else 0.0), 3)}
                for i, c in enumerate(greedy_curve)]
    knee = next((c["k"] for c in greedy_curve if c["union_rate"] >= full_union), len(names))

    # expected random-k coverage (order-independent): mean union rate over all k-subsets
    expected_k = {}
    for k in range(1, len(names) + 1):
        subs = list(combinations(names, k))
        expected_k[k] = round(sum(_union_rate(solves, s, n) for s in subs) / len(subs), 3)

    rep = {
        "experiment": "issue_replay_coverage_scaling", "corpus": args.corpus, "n_bundles": n,
        "agents": names, "full_pool_union_rate": round(full_union, 3),
        "greedy_best_curve": greedy_curve, "greedy_marginal_lift": marginal,
        "smallest_pool_reaching_union": knee,
        "expected_union_rate_by_pool_size": expected_k,
        "single_agent_mean": expected_k.get(1),
        "takeaway": (f"greedy pool reaches the union ({round(full_union,3)}) at {knee} agents; "
                     "the curve's marginal lift shows where adding agents stops paying."),
        "evidence_tier": "offline over real per-agent solve vectors; no model calls",
    }
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== COVERAGE SCALING (corpus={args.corpus}, n={n}, agents={len(names)}) ===")
    print(f"full-pool union = {full_union:.3f}; reached at {knee} agents (greedy)")
    print("greedy curve:", [(c["k"], c["added"], c["union_rate"]) for c in greedy_curve])
    print("marginal lift:", [(m["k"], m["marginal_lift"]) for m in marginal])
    print("expected union by random pool size:", expected_k)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
