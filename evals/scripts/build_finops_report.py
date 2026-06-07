"""Build the FinOps report from the latest MetaRouter Arena run (GOALS Alpha 42 P6).

Deterministic (no API calls): reads reports/metarouter_arena.json and writes
reports/finops_cost_per_verified_success.json — cost attribution, verified-success-per-dollar
ranking, and Pareto promotion decisions vs the incumbent router.
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.finops import finops_report

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    arena_path = ROOT / "reports" / "metarouter_arena.json"
    if not arena_path.exists():
        print(f"[skip] {arena_path} not found — run the arena first")
        return 0
    arena = json.loads(arena_path.read_text())
    report = finops_report(arena, incumbent="cheap_single")
    out = ROOT / "reports" / "finops_cost_per_verified_success.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"best value policy: {report['best_value_policy']}")
    print(f"ranking by verified success / $: {report['ranking_by_verified_success_per_dollar']}")
    print(f"promotable over {report['incumbent']}: {report['promotable_policies']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
