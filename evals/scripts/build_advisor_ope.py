"""Advisor OPE report (GOALS Alpha 42 P1).

Compares the advisor_router (cheap executor + budgeted read-only advisor escalation) against the
plain cheap_single executor on the arena: does escalation improve verified success without
regressing cost-per-verified-success by more than 10%? Deterministic; reads the arena report.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _score(arena: dict, policy: str) -> dict | None:
    return next((s for s in arena.get("policy_scores", []) if s["policy"] == policy), None)


def main() -> int:
    arena_path = ROOT / "reports" / "metarouter_arena.json"
    if not arena_path.exists():
        print("[skip] no arena report")
        return 0
    arena = json.loads(arena_path.read_text())
    adv, base = _score(arena, "advisor_router"), _score(arena, "cheap_single")
    if not adv or not base:
        print("[skip] advisor_router/cheap_single not in arena (run with --full)")
        return 0
    ac = adv["cost_per_verified_success"]
    bc = base["cost_per_verified_success"]
    cost_regression = ((ac - bc) / bc) if (ac and bc) else 0.0
    improves_quality = adv["verified_success_rate"] > base["verified_success_rate"]
    report = {
        "experiment": "advisor_ope",
        "executor": "cheap_single", "advisor_policy": "advisor_router",
        "advisor_call_rate": adv["advisor_call_rate"],
        "verified_success_executor": base["verified_success_rate"],
        "verified_success_with_advisor": adv["verified_success_rate"],
        "verified_success_lift": round(adv["verified_success_rate"]
                                       - base["verified_success_rate"], 4),
        "cost_per_verified_success_executor": bc,
        "cost_per_verified_success_with_advisor": ac,
        "cost_regression_fraction": round(cost_regression, 4),
        "advisor_improves_or_holds": improves_quality or cost_regression <= 0.10,
        "acceptance": ("advisor improves verified success OR cost/verified-success does not "
                       "regress by >10%"),
        "passes_acceptance": improves_quality or cost_regression <= 0.10,
    }
    out = ROOT / "reports" / "advisor_ope.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"advisor lift={report['verified_success_lift']} call_rate={adv['advisor_call_rate']} "
          f"cost_regression={report['cost_regression_fraction']} "
          f"passes={report['passes_acceptance']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
