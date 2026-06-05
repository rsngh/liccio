"""Build the timeout-confound artifact from two committed live baselines (Alpha 23 WS8).

Reads the graded-benchmark baseline measured at the tight 180s cap (benchmark_baseline.json,
solve 0.667) and the baseline arm of the A/B measured at the fair 240s cap
(benchmark_skill_ab.json overall.baseline = 1.0), and classifies whether the gap is
infra-confounded. Both inputs are real committed live measurements, so no new harness run
is needed. Writes reports/live/timeout_confound.json (redacted).
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.evaluation.infra_confound import detect_timeout_confound
from acp.observability.live_report import redact_report

LOW_TIMEOUT = 180
HIGH_TIMEOUT = 240


def main() -> int:
    base = json.loads(Path("reports/live/benchmark_baseline.json").read_text())
    ab = json.loads(Path("reports/live/benchmark_skill_ab.json").read_text())
    low = float(base["overall_solve_rate"])
    high = float(ab["overall"]["baseline"])  # baseline arm @240s
    v = detect_timeout_confound(LOW_TIMEOUT, low, HIGH_TIMEOUT, high)
    report = {
        "experiment": "ws8_timeout_confound",
        "harness": base.get("harness", "claude_code"),
        "low": {"timeout_s": LOW_TIMEOUT, "solve_rate": low,
                "by_difficulty": base.get("by_difficulty", {})},
        "high": {"timeout_s": HIGH_TIMEOUT, "solve_rate": high},
        "verdict": v.to_dict(),
    }
    out = Path("reports/live/timeout_confound.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    print(f"timeout confound [{report['harness']}]: {low} @{LOW_TIMEOUT}s -> {high} "
          f"@{HIGH_TIMEOUT}s | confounded={v.confounded}")
    print(f"  {v.recommendation}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
