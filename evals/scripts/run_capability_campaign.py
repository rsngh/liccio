"""Capability matrix population campaign runner (Alpha 8, WS13).

Generates a large deterministic synthetic bakeoff campaign, populates a
:class:`~acp.routing.capability_matrix.CapabilityMatrix`, and writes the matrix
plus its coverage summary to ``evals/reports/capability_matrix_populated.json``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.evaluation.capability_campaign import (
    campaign_summary,
    generate_campaign_report,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repetitions", type=int, default=6)
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument(
        "--out-json",
        default="evals/reports/capability_matrix_populated.json",
    )
    args = ap.parse_args()

    matrix = generate_campaign_report(
        repetitions=args.repetitions, seed_offset=args.seed_offset
    )
    summary = campaign_summary(matrix)

    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"matrix": matrix.to_dict(), "summary": summary}, indent=2)
    )
    print(
        f"n_cells={summary['n_cells']} "
        f"n_sufficient={summary['n_sufficient']} "
        f"n_under_sampled={summary['n_under_sampled']}"
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
