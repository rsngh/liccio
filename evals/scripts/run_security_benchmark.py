"""Security & prompt-injection benchmark runner (Alpha-8 WS18).

Runs the adversarial payload benchmark across the deterministic adapter layer
and writes evals/reports/security_benchmark.json.

    uv run python evals/scripts/run_security_benchmark.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.evaluation.security_benchmark import DEFAULT_SECRET, run_security_benchmark

REPORT = Path("evals/reports/security_benchmark.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adapters", nargs="*", default=["fake", "patch"],
        help="adapter names to record in the report (benchmark is adapter-agnostic)",
    )
    parser.add_argument(
        "--secret", default=DEFAULT_SECRET,
        help="planted secret value that must never leak into the report",
    )
    parser.add_argument("--out", type=Path, default=REPORT, help="output report path")
    args = parser.parse_args()

    report = run_security_benchmark(adapters=args.adapters, secret=args.secret)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    s = report["summary"]
    print(
        f"security benchmark: {s['n_attacks']} attacks; escalated={s['n_escalated']} "
        f"flagged={s['n_flagged']} all_handled={s['all_handled']} "
        f"any_secret_leak={s['any_secret_leak']}"
    )
    return 0 if s["all_handled"] and not s["any_secret_leak"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
