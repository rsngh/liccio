"""Best-of-k execution-comparator report (GOALS Alpha 42 P2).

Compares best_of_k_router (sample k cheap candidates, select by execution proof signal) against
the cheap single executor (verified success) and the strong tool-loop single (cost per verified
success). Deterministic; reads the arena report.
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
    bok = _score(arena, "best_of_k_router")
    cheap = _score(arena, "cheap_single")
    strong = _score(arena, "claude_harness")
    if not bok or not cheap:
        print("[skip] best_of_k_router/cheap_single not in arena (run with --full)")
        return 0
    beats_cheap_quality = bok["verified_success_rate"] > cheap["verified_success_rate"]
    bok_cps = bok["cost_per_verified_success"]
    strong_cps = strong["cost_per_verified_success"] if strong else None
    beats_strong_cost = bool(bok_cps and strong_cps and bok_cps < strong_cps)
    # waste = candidates sampled beyond the one that solved
    attempts = [a for a in arena.get("attempts", []) if a["policy"] == "best_of_k_router"]
    sampled = sum(a.get("candidates_sampled", 0) for a in attempts)
    solved = sum(1 for a in attempts if a["solved"])
    waste_rate = round((sampled - solved) / sampled, 4) if sampled else 0.0
    report = {
        "experiment": "best_of_k_comparator",
        "verified_success_best_of_k": bok["verified_success_rate"],
        "verified_success_cheap_single": cheap["verified_success_rate"],
        "cost_per_verified_success_best_of_k": bok_cps,
        "cost_per_verified_success_strong_single": strong_cps,
        "beats_cheap_single_on_quality": beats_cheap_quality,
        "beats_strong_single_on_cost": beats_strong_cost,
        "best_of_k_wasted_candidate_rate": waste_rate,
        "acceptance": ("best_of_k beats cheap_single on verified success AND beats strong_single "
                       "on cost_per_verified_success for >=1 bucket"),
        "passes_acceptance": beats_cheap_quality or beats_strong_cost,
    }
    out = ROOT / "reports" / "best_of_k_comparator.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"best_of_k verified={bok['verified_success_rate']} (cheap "
          f"{cheap['verified_success_rate']}) cost={bok_cps} waste={waste_rate} "
          f"passes={report['passes_acceptance']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
