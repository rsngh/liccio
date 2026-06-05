"""Graded benchmark baseline — live capability-by-difficulty (Alpha 23 WS4).

Runs a real vendor harness (Claude Code, headless + fast) over the graded bugfix suite
with NO skill, and reports the honest solve rate overall and per difficulty. This
establishes whether the suite has headroom (baseline < 1.0 on some tier) so a skill could
show measurable lift, or whether the harness is at ceiling (an honest finding too). Writes
reports/live/benchmark_baseline.json (redacted, secret-scanned).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from acp.agents.vendor_native import VendorNativeHarness
from acp.evaluation.benchmark_runner import run_benchmark
from acp.observability.live_report import redact_report

HARNESS = "claude_code"


def main() -> int:
    if shutil.which("claude") is None:
        print("[skip] claude (Claude Code) not on PATH")
        return 0
    harness = VendorNativeHarness(HARNESS)
    result = run_benchmark(harness, timeout_s=180, reps=1)
    report = {"experiment": "ws4_benchmark_baseline", **result.to_dict()}
    out = Path("reports/live/benchmark_baseline.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"benchmark baseline [{HARNESS}]: overall={result.overall_solve_rate} "
          f"(n_conclusive={result.n_conclusive}/{result.n_attempts})")
    for diff, agg in result.by_difficulty.items():
        print(f"  {diff:7s}: solve_rate={agg['solve_rate']} "
              f"(n={agg['n_conclusive']}/{agg['n_attempts']})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
