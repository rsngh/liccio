"""Data-driven capability probe: is there a REAL gap between haiku, sonnet, and opus?

Before claiming a metarouter can "route cheap->strong by difficulty," we must first prove the
tiers actually differ in capability. If haiku already solves everything, the honest finding is
"use haiku, save 15x" — and no escalation policy can beat that. This runs each capability-gradient
task single-shot (minimal context, so the ONLY lever is model strength) across all three tiers for
N trials, reporting per-tier, per-difficulty solve rate with Wilson CIs.

Run:  python -m evals.hetero_arena.probe --trials 3
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from evals.hetero_arena.tier_tasks import capability_tasks
from evals.hetero_arena.tiers import HAIKU, OPUS, SONNET
from evals.metarouter_arena.policies import _single_shot
from evals.metarouter_arena.statistics import wilson_ci

from acp.agents.claude_agent import ClaudeAgentAdapter

TIERS = (HAIKU, SONNET, OPUS)


def run_probe(trials: int = 3) -> dict:
    tasks = capability_tasks()
    adapters = {t.name: ClaudeAgentAdapter(name=t.name, model=t.model) for t in TIERS}
    # per (tier, task): list of (solved, conclusive, cost, latency)
    cells: dict[tuple[str, str], list] = defaultdict(list)
    t_start = time.time()
    with tempfile.TemporaryDirectory(prefix="hetero_probe_") as td:
        root = Path(td)
        for trial in range(trials):
            for spec in tasks:
                for tier in TIERS:
                    att = _single_shot(adapters[tier.name], spec, root, strategy="minimal",
                                       policy_name=f"probe_{tier.name}_{trial}",
                                       cost_fn=tier.cost)
                    cells[(tier.name, spec.name)].append(
                        (att.solved, att.conclusive, att.cost_usd, att.latency_s))
                    flag = "ok " if att.solved else ("--" if att.conclusive else "??")
                    print(f"[t{trial}] {tier.name:6} {spec.name:18} {flag} "
                          f"${att.cost_usd:.5f} {att.latency_s:.1f}s", flush=True)

    # aggregate per tier+difficulty and per tier overall
    diff_of = {s.name: s.difficulty_band for s in tasks}
    per_tier_diff: dict[tuple[str, str], list[int]] = defaultdict(list)  # (tier,diff)->solved flags
    per_tier: dict[str, list[int]] = defaultdict(list)
    per_tier_cost: dict[str, float] = defaultdict(float)
    per_tier_conc: dict[str, int] = defaultdict(int)
    for (tier_name, task_name), runs in cells.items():
        for solved, conclusive, cost, _lat in runs:
            per_tier_cost[tier_name] += cost
            if conclusive:
                per_tier_conc[tier_name] += 1
                per_tier[tier_name].append(1 if solved else 0)
                per_tier_diff[(tier_name, diff_of[task_name])].append(1 if solved else 0)

    def summ(flags: list[int]) -> dict:
        n = len(flags)
        s = sum(flags)
        p, lo, hi = wilson_ci(s, n)
        return {"n": n, "solved": s, "rate": p, "ci": [lo, hi]}

    report = {
        "kind": "capability_probe",
        "trials": trials,
        "n_tasks": len(tasks),
        "elapsed_s": round(time.time() - t_start, 1),
        "per_tier": {t.name: summ(per_tier[t.name]) for t in TIERS},
        "per_tier_total_cost_usd": {k: round(v, 6) for k, v in per_tier_cost.items()},
        "per_tier_by_difficulty": {
            f"{t.name}/{d}": summ(per_tier_diff[(t.name, d)])
            for t in TIERS for d in ("easy", "medium", "hard")
            if per_tier_diff[(t.name, d)]
        },
        "per_task": {
            f"{t.name}/{s.name}": summ([1 if r[0] else 0 for r in cells[(t.name, s.name)] if r[1]])
            for t in TIERS for s in tasks
        },
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--out", default="reports/hetero_probe.json")
    args = ap.parse_args()
    rep = run_probe(args.trials)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, indent=2))
    print("\n=== CAPABILITY PROBE ===")
    for tier, s in rep["per_tier"].items():
        print(f"{tier:6} overall  {s['rate']:.2f}  CI{s['ci']}  (n={s['n']})  "
              f"${rep['per_tier_total_cost_usd'].get(tier,0):.4f}")
    print("--- by difficulty ---")
    for k, s in rep["per_tier_by_difficulty"].items():
        print(f"{k:16} {s['rate']:.2f}  CI{s['ci']}  (n={s['n']})")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
