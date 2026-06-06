"""Repo-replay live bakeoff (Alpha 29) — realistic bug shapes, activation-aware.

Runs the weak model (gpt-4o-mini, blind generator + hidden-test proof signal) over the
realistic repo-replay tasks: single-shot reliability vs best-of-5, with the 4-denominator
solve-rate breakdown and an honest evidence tier (fixture: real-world-shaped, not scraped
history). Writes evals/reports/repo_replay_live.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from acp.agents.repo_replay import REPLAY_TASKS
from acp.agents.weak_model_candidates import DEFAULT_WEAK_MODEL, best_of_k, openai_sampler
from acp.core.config import get_settings
from acp.evaluation.evidence_quality import EvidenceTier, solve_rate_breakdown, stamp_evidence
from acp.observability.live_report import redact_report

REPS = 5
K = 5


def main() -> int:
    if get_settings().openai_api_key is None:
        print("[skip] ACP_OPENAI_API_KEY not set")
        return 0
    sampler = openai_sampler(model=DEFAULT_WEAK_MODEL, temperature=0.9)
    rows = []
    cells = []
    ss_total = ss_pass = bok_solved = 0
    for task in REPLAY_TASKS:
        bench = task.as_bench_task()
        ss = [best_of_k(bench, k=1, sampler=sampler, model=DEFAULT_WEAK_MODEL)
              for _ in range(REPS)]
        ss_solved = sum(r.solved for r in ss)
        ss_total += REPS
        ss_pass += ss_solved
        for r in ss:
            # Propagate the attempt's own outcome so an INCONCLUSIVE candidate (e.g. the
            # provider SDK/endpoint was unavailable -> n_conclusive == 0) is NOT silently
            # counted as a conclusive task failure. Without this, an unreachable provider
            # contaminates solve_rate_conclusive and reads as "the model failed every task".
            cells.append({"success": r.solved, "is_harness": False,
                          "tool_calls": 1 if r.n_conclusive else 0,
                          "diff_captured": r.n_conclusive > 0,
                          "_outcome": r.outcome,
                          "status": "succeeded" if r.solved else "failed",
                          "measurement_quality": 1.0 if r.n_conclusive else 0.0})
        bok = best_of_k(bench, k=K, sampler=sampler, model=DEFAULT_WEAK_MODEL)
        bok_solved += int(bok.solved)
        rows.append({"task": task.name, "single_shot": f"{ss_solved}/{REPS}",
                     "best_of_k_solved": bok.solved})
        print(f"{task.name:16s} single_shot={ss_solved}/{REPS} best_of_{K}={bok.solved}")
    b = solve_rate_breakdown(cells)
    ss_rate = round(ss_pass / ss_total, 4) if ss_total else 0.0
    bok_rate = round(bok_solved / len(REPLAY_TASKS), 4) if REPLAY_TASKS else 0.0
    n_inconclusive = ss_total - b.n_conclusive
    # No conclusive measurement was obtained -> the raw rate is meaningless; flag it loudly
    # instead of publishing a contaminated "0.0 solve rate" that looks like a model verdict.
    measurement_contaminated = b.n_conclusive == 0 and ss_total > 0
    report = {"experiment": "repo_replay_live", "model": DEFAULT_WEAK_MODEL,
              "n_tasks": len(REPLAY_TASKS), "single_shot_rate": ss_rate,
              "single_shot_rate_conclusive": b.solve_rate_conclusive,
              "n_conclusive": b.n_conclusive, "n_inconclusive": n_inconclusive,
              "measurement_contaminated": measurement_contaminated,
              "best_of_k_rate": bok_rate, "best_of_k_lift": round(bok_rate - ss_rate, 4),
              "ceiling_escaped": ss_rate < 1.0,
              "solve_rate_breakdown": b.to_dict(), "rows": rows}
    # honest tier: real-world-SHAPED fixtures, not scraped real-repo history
    report = stamp_evidence(report, EvidenceTier.FIXTURE)
    out = Path("evals/reports/repo_replay_live.json")
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"\nsingle_shot_rate={ss_rate} best_of_{K}_rate={bok_rate} "
          f"lift={report['best_of_k_lift']} ceiling_escaped={report['ceiling_escaped']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
