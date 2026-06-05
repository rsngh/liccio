"""Topology controller search artifacts (Alpha 24 area 3, offline).

Builds a representative trace dataset (graded difficulty × risk, including security tasks
that require strict verification and ambiguous tasks), runs the offline controller search,
and writes: topology_controller_search.json (best vs hand-rule baseline),
topology_ope.json (all candidate offline estimates), and topology_policy_canary.json (the
found controller is canary-gated before promotion — never auto-deployed).
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.routing.topology_controller import TopologyTrace, search_controllers

ROOT = Path("evals/reports")


def _traces() -> list[TopologyTrace]:
    t: list[TopologyTrace] = []
    # easy/low-risk: planner+retrieval skippable, succeed
    for _ in range(8):
        t.append(TopologyTrace("bugfix", "low", "easy", False, True, False))
    # medium tasks
    for _ in range(6):
        t.append(TopologyTrace("refactor", "medium", "medium", False, True, False))
    # hard tasks (some fail — parallel branching could help but costs)
    for i in range(6):
        t.append(TopologyTrace("bugfix", "medium", "hard", False, i % 3 != 0, False))
    # security / high-risk: strict verify required
    for _ in range(4):
        t.append(TopologyTrace("security_fix", "high", "medium", False, True, True))
    # ambiguous tasks: need spec/advisor first
    for _ in range(3):
        t.append(TopologyTrace("feature", "medium", "medium", True, True, False))
    return t


def main() -> int:
    traces = _traces()
    res = search_controllers(traces)
    ROOT.mkdir(parents=True, exist_ok=True)

    search = {"experiment": "topology_controller_search", "n_traces": len(traces),
              "baseline": res.baseline.to_dict(), "best": res.best.to_dict(),
              "improved": res.improved, "n_candidates": res.n_candidates,
              "n_safe": res.n_safe}
    ope = {"experiment": "topology_ope", "n_traces": len(traces),
           "candidates": [s.to_dict() for s in sorted(
               res.all_scores, key=lambda s: (not s.safe, s.est_cost))]}
    canary = {"experiment": "topology_policy_canary",
              "candidate_controller": res.best.key,
              "improved_offline": res.improved,
              "requires_canary_before_promotion": True,
              "guardrails": ["security never skips strict verify",
                             "ambiguous routes to advisor first",
                             "staged canary 5/25/50/100 with rollback"],
              "auto_deployed": False}
    for name, data in (("topology_controller_search.json", search),
                       ("topology_ope.json", ope),
                       ("topology_policy_canary.json", canary)):
        (ROOT / name).write_text(json.dumps(data, indent=2) + "\n")
        print(f"wrote {ROOT / name}")
    print(f"baseline cost={res.baseline.est_cost} success={res.baseline.est_success} -> "
          f"best cost={res.best.est_cost} success={res.best.est_success} improved={res.improved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
