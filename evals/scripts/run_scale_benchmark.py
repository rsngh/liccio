"""Storage & scale benchmark runner (Alpha 8, WS17).

Seeds fresh temp DBs at several sizes N, times the core storage workflows, and
writes a JSON report to evals/reports/storage_scale.json. Defaults are small so
CI stays fast; pass larger ``--sizes`` for a deeper scaling sweep.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.evaluation.scale_benchmark import run_scale_benchmark


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[50, 100, 200])
    ap.add_argument("--out-json", default="evals/reports/storage_scale.json")
    args = ap.parse_args()

    report = run_scale_benchmark(sizes=args.sizes)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2))

    for row in report["per_n"]:
        lat = row["latency_ms"]
        print(f"N={row['n']:>6} entities={row['total_entities']:>7} "
              f"db={row['db_size_bytes']:>9}B exhaust={lat['build_exhaust_bundle']:.2f}ms "
              f"ope={lat['ope_samples']:.2f}ms")
    print(f"subquadratic={report['subquadratic']} "
          f"by_op={report['subquadratic_by_operation']}")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
