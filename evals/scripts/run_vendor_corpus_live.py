"""Vendor-native corpus campaign (Alpha 26).

Turns vendor proof from a 2-task smoke test into a real capability matrix: runs the
Claude Code vendor harness across the FULL task corpus (graded easy/medium/hard + the hard
greedy-trap cohort), with and without the full-suite-discipline skill, and aggregates solve
rate by difficulty via the measurement-trust hygiene layer (conclusive only; timeouts are
infra). Writes evals/reports/vendor_capability_matrix.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.agents.hard_tasks import HARD_TASKS
from acp.agents.vendor_native import VendorNativeHarness
from acp.evaluation.benchmark_runner import run_benchmark
from acp.observability.live_report import redact_report

HARNESS = "claude_code"
CORPUS = BENCH_TASKS + HARD_TASKS
SKILL = ("# full-suite discipline\n- Run the FULL pytest suite and fix EVERY failing test; "
         "for algorithmic bugs prefer a correct dynamic-programming solution over greedy.\n")


def main() -> int:
    if shutil.which("claude") is None:
        print("[skip] claude (Claude Code) not on PATH")
        return 0
    harness = VendorNativeHarness(HARNESS)
    baseline = run_benchmark(harness, tasks=CORPUS, timeout_s=240, reps=1)
    skilled = run_benchmark(harness, tasks=CORPUS, skill_content=SKILL, timeout_s=240, reps=1)
    report = {
        "experiment": "vendor_capability_matrix", "harness": HARNESS,
        "n_tasks": len(CORPUS),
        "baseline": {"overall": baseline.overall_solve_rate,
                     "by_difficulty": baseline.by_difficulty,
                     "n_conclusive": baseline.n_conclusive, "tasks": baseline.tasks},
        "with_skill": {"overall": skilled.overall_solve_rate,
                       "by_difficulty": skilled.by_difficulty,
                       "n_conclusive": skilled.n_conclusive},
        "skill_lift": round(skilled.overall_solve_rate - baseline.overall_solve_rate, 4),
    }
    out = Path("evals/reports/vendor_capability_matrix.json")
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"vendor [{HARNESS}] corpus n={len(CORPUS)}: baseline overall="
          f"{baseline.overall_solve_rate} with_skill={skilled.overall_solve_rate} "
          f"lift={report['skill_lift']}")
    for d, agg in baseline.by_difficulty.items():
        print(f"  {d:7s}: {agg['solve_rate']} (n={agg['n_conclusive']}/{agg['n_attempts']})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
