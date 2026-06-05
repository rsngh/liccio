"""Best-of-k on genuinely HARD tasks — escape the ceiling (Alpha 25, test F).

Measures single-shot reliability vs best-of-k on the hard greedy-trap cohort with a live
weak model (blind generator + held-out pytest proof signal). If these tasks are genuinely
hard, single-shot solve rate < 1.0 and best-of-k + execution selection lifts it — the
first non-ceiling evidence that sampling many cheap candidates + a verifier buys solve rate.
Writes evals/reports/hard_best_of_k.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from acp.agents.hard_tasks import HARD_TASKS
from acp.agents.weak_model_candidates import DEFAULT_WEAK_MODEL, best_of_k, openai_sampler
from acp.core.config import get_settings
from acp.observability.live_report import redact_report

SINGLE_SHOT_REPS = 5
BEST_OF_K = 8
MODEL = DEFAULT_WEAK_MODEL


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    sampler = openai_sampler(model=MODEL, temperature=0.9)
    rows = []
    ss_total = ss_pass = 0
    bok_solved = 0
    total_cost = 0.0
    for task in HARD_TASKS:
        # single-shot reliability: SINGLE_SHOT_REPS independent k=1 attempts
        ss = [best_of_k(task, k=1, sampler=sampler, model=MODEL)
              for _ in range(SINGLE_SHOT_REPS)]
        ss_solved = sum(r.solved for r in ss)
        ss_total += SINGLE_SHOT_REPS
        ss_pass += ss_solved
        # best-of-k: one k=BEST_OF_K attempt with execution selection
        bok = best_of_k(task, k=BEST_OF_K, sampler=sampler, model=MODEL)
        bok_solved += int(bok.solved)
        total_cost += sum(r.total_cost for r in ss) + bok.total_cost
        rows.append({"task": task.name,
                     "single_shot_rate": round(ss_solved / SINGLE_SHOT_REPS, 4),
                     "best_of_k_solved": bok.solved, "best_of_k_n_passed": bok.n_passed,
                     "k": BEST_OF_K})
        print(f"{task.name:14s} single_shot={ss_solved}/{SINGLE_SHOT_REPS} "
              f"best_of_{BEST_OF_K}={'PASS' if bok.solved else 'fail'} "
              f"(passed {bok.n_passed}/{BEST_OF_K})")
    single_shot_rate = round(ss_pass / ss_total, 4) if ss_total else 0.0
    best_of_k_rate = round(bok_solved / len(HARD_TASKS), 4) if HARD_TASKS else 0.0
    report = {"experiment": "hard_best_of_k", "model": MODEL,
              "single_shot_reps": SINGLE_SHOT_REPS, "k": BEST_OF_K,
              "single_shot_rate": single_shot_rate, "best_of_k_rate": best_of_k_rate,
              "best_of_k_lift": round(best_of_k_rate - single_shot_rate, 4),
              "ceiling_escaped": single_shot_rate < 1.0,
              "total_cost": round(total_cost, 6), "rows": rows}
    out = Path("evals/reports/hard_best_of_k.json")
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"\nsingle_shot_rate={single_shot_rate} best_of_{BEST_OF_K}_rate={best_of_k_rate} "
          f"lift={report['best_of_k_lift']} ceiling_escaped={report['ceiling_escaped']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
