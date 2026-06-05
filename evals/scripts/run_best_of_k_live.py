"""Weak-model best-of-k live bakeoff + cost curve (Alpha 24 area 2).

Runs the weak model (gpt-4o-mini) over the graded benchmark at k = 1, 4, 8, selecting by
execution proof, and measures solve rate and cost-per-conclusive-success at each k. The
thesis under test: does sampling more cheap candidates + execution selection buy solve
rate cost-effectively? Writes evals/reports/weak_model_candidate_bakeoff.json and
evals/reports/best_of_k_cost_curve.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS, UNDERSPECIFIED_TASKS
from acp.agents.weak_model_candidates import DEFAULT_WEAK_MODEL, best_of_k, openai_sampler
from acp.core.config import get_settings
from acp.observability.live_report import redact_report

KS = (1, 4, 8)
MODEL = DEFAULT_WEAK_MODEL
# Two cohorts: single-bug graded tasks (the weak model usually solves single-shot) and
# underspecified tasks (prompt names one bug, a second lurks — single-shot is unreliable,
# so best-of-k + execution selection should buy solve rate).
COHORTS = {"graded": BENCH_TASKS, "underspecified": UNDERSPECIFIED_TASKS}


def _cohort_curve(tasks, sampler) -> tuple[dict, list]:
    by_k: dict[str, dict] = {}
    rows: list[dict] = []
    for k in KS:
        results = [best_of_k(t, k=k, sampler=sampler, model=MODEL) for t in tasks]
        conclusive = [r for r in results if r.n_conclusive > 0]
        solved = [r for r in conclusive if r.solved]
        cost = sum(r.total_cost for r in results)
        solve_rate = round(len(solved) / len(conclusive), 4) if conclusive else 0.0
        cpcs = round(cost / len(solved), 6) if solved else None
        by_k[str(k)] = {"k": k, "n_tasks": len(results), "n_conclusive": len(conclusive),
                        "n_solved": len(solved), "solve_rate": solve_rate,
                        "total_cost": round(cost, 6), "cost_per_conclusive_success": cpcs,
                        "mean_diversity": round(
                            sum(r.diversity for r in results) / len(results), 4)}
        rows.append(by_k[str(k)])
    return by_k, rows


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    sampler = openai_sampler(model=MODEL, temperature=0.8)
    by_cohort: dict[str, dict] = {}
    all_rows: list[dict] = []
    for name, tasks in COHORTS.items():
        by_k, rows = _cohort_curve(tasks, sampler)
        by_cohort[name] = by_k
        for r in rows:
            r["cohort"] = name
            all_rows.append(r)
            print(f"[{name}] k={r['k']}: solve_rate={r['solve_rate']} "
                  f"cost=${r['total_cost']} cpcs={r['cost_per_conclusive_success']} "
                  f"diversity={r['mean_diversity']}")

    bakeoff = {"experiment": "weak_model_candidate_bakeoff", "model": MODEL,
               "ks": list(KS), "by_cohort": by_cohort}
    u = by_cohort["underspecified"]
    curve = {"experiment": "best_of_k_cost_curve", "model": MODEL, "rows": all_rows,
             "underspecified_best_of_k_lift": round(
                 u[str(KS[-1])]["solve_rate"] - u[str(KS[0])]["solve_rate"], 4)}
    for path, data in (("evals/reports/weak_model_candidate_bakeoff.json", bakeoff),
                       ("evals/reports/best_of_k_cost_curve.json", curve)):
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(redact_report(data), indent=2) + "\n")
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            secret = os.environ.get(key)
            if secret:
                assert secret not in out.read_text(), f"{key} leaked!"
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
