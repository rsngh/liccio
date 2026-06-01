"""Context retrieval benchmark runner (round-1 two-day D2B2).

Generates a synthetic repo, runs the benchmark across strategies, and writes
JSON + Markdown reports to evals/reports/.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from acp.evaluation.retrieval_benchmark import (
    generate_synthetic_repo,
    report_to_markdown,
    run_benchmark,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=200)
    ap.add_argument("--strategy", default="hybrid_keyword_embedding")
    ap.add_argument("--out-json", default="evals/reports/context_benchmark.json")
    ap.add_argument("--out-md", default="evals/reports/context_benchmark.md")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    repo = tmp / "synthetic"
    gold = generate_synthetic_repo(repo, n_files=args.files)
    rep = run_benchmark(repo, gold, strategy=args.strategy)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(rep.to_dict(), indent=2))
    Path(args.out_md).write_text(report_to_markdown(rep))
    print(f"recall@5={rep.recall_at_5:.3f} recall@10={rep.recall_at_10:.3f} "
          f"mrr={rep.mrr:.3f} leak={rep.secret_leakage_count}")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
