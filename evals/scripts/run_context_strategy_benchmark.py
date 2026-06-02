"""Context-strategy benchmark runner (Alpha 6, WS5).

Sweeps retrieval strategies over multiple synthetic repo fixtures, picks the
best strategy per repo, and writes JSON + Markdown reports to evals/reports/.
Runs fully offline with the default hashing embedder (no network / API key).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.evaluation.context_strategy_benchmark import (
    DEFAULT_STRATEGIES,
    report_to_markdown,
    run_context_strategy_benchmark,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--strategies",
        nargs="*",
        default=list(DEFAULT_STRATEGIES),
        help="strategies to sweep (default: a representative spread)",
    )
    ap.add_argument("--out-json", default="evals/reports/context_strategy_benchmark.json")
    ap.add_argument("--out-md", default="evals/reports/context_strategy_benchmark.md")
    args = ap.parse_args()

    report = run_context_strategy_benchmark(strategies=args.strategies)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report.to_dict(), indent=2))
    Path(args.out_md).write_text(report_to_markdown(report))

    for repo, strat in report.best_per_repo.items():
        print(f"best[{repo}] = {strat}")
    if report.overall_ranking:
        print(f"overall winner = {report.overall_ranking[0]['strategy']}")
    print(f"total secret leakage = {report.total_secret_leakage}")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
