"""Large empirical corpus runner (Alpha 10, WS11).

Generates a large deterministic synthetic-bakeoff corpus, derives its capability
coverage / preference-pair / Pareto-frontier statistics, and writes the report to
``evals/reports/large_empirical_corpus.json``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.evaluation.large_corpus import corpus_headline, generate_large_corpus


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repetitions", type=int, default=8)
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument(
        "--out-json",
        default="evals/reports/large_empirical_corpus.json",
    )
    args = ap.parse_args()

    corpus = generate_large_corpus(
        repetitions=args.repetitions, seed_offset=args.seed_offset
    )

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corpus, indent=2))

    print(corpus_headline(corpus))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
