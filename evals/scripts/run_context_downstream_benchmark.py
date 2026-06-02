"""Context-strategy DOWNSTREAM benchmark runner (Alpha 7, WS7).

Runs each fixture task through an ``AppService`` under several pinned context
strategies and repetitions, scoring strategies by DOWNSTREAM task success (run
status / verification / reward / cost / latency) plus retrieval recall as a
tiebreak, then writes JSON + Markdown reports to ``evals/reports/``. Runs fully
offline with the deterministic patch agent (no network / API key).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.evaluation.context_downstream_benchmark import (
    DEFAULT_STRATEGIES,
    report_to_markdown,
    run_context_downstream_benchmark,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--strategies",
        nargs="*",
        default=list(DEFAULT_STRATEGIES),
        help="context strategies to compare downstream (default: a small spread)",
    )
    ap.add_argument(
        "--repetitions", type=int, default=2, help="repetitions per (task, strategy)"
    )
    ap.add_argument(
        "--out-json", default="evals/reports/context_downstream_benchmark.json"
    )
    ap.add_argument("--out-md", default="evals/reports/context_downstream_benchmark.md")
    args = ap.parse_args()

    report = run_context_downstream_benchmark(
        strategies=args.strategies, repetitions=args.repetitions
    )

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report.to_dict(), indent=2))
    Path(args.out_md).write_text(report_to_markdown(report))

    print(f"best strategy (downstream) = {report.best_strategy}")
    for a in report.aggregates:
        print(
            f"  {a['strategy']}: success={a['success_rate']} "
            f"verify={a['verification_pass_rate']} reward={a['mean_reward']} "
            f"recall={a['mean_gold_recall']}"
        )
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
