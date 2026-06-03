"""Mixed empirical corpus runner (Alpha 11, WS12).

Generates the wider mixed deterministic synthetic-bakeoff corpus (task types x
risk levels x repo types x adapters x context strategies x repetitions), derives
its coverage / preference-pair / Pareto-frontier / counterfactual-regret
statistics, and writes the report to
``evals/reports/mixed_empirical_corpus.json``.

The default scale is ``full`` (the Alpha-11 sizing: thousands of tasks, 20 repo
types). It is pure arithmetic with no network, so it finishes in a few seconds;
pass ``--scale test`` for the tiny slice the test suite uses.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.evaluation.mixed_corpus import generate_mixed_corpus, mixed_corpus_headline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scale",
        choices=("test", "full"),
        default="full",
        help="corpus sizing (default: full = Alpha-11 target)",
    )
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument(
        "--out-json",
        default="evals/reports/mixed_empirical_corpus.json",
    )
    args = ap.parse_args()

    corpus = generate_mixed_corpus(scale=args.scale, seed_offset=args.seed_offset)

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corpus, indent=2))

    print(mixed_corpus_headline(corpus))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
