"""Build the offline topology-controller-search report from the arena (GOALS Alpha 42 P3).

Deterministic, no live calls: maps arena policies to topology actions, joins with each task's
context_need + risk, and searches a controller over the pre-collected trajectories. Writes
reports/topology_controller_search.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from acp.routing.topology_controller_search import (  # noqa: E402
    ControllerCell,
    TopologyControllerSearch,
)

_POLICY_TO_ACTION = {
    "cheap_single": "cheap_single", "repo_map_router": "retry_with_repo_map",
    "claude_harness": "strong_single", "advisor_router": "ask_advisor",
    "best_of_k_router": "best_of_k",
}


def main() -> int:
    arena_path = ROOT / "reports" / "metarouter_arena.json"
    if not arena_path.exists():
        print("[skip] no arena report")
        return 0
    arena = json.loads(arena_path.read_text())
    from evals.metarouter_arena.task_pack import TASK_PACK
    meta = {t.name: (t.context_need, t.risk_level) for t in TASK_PACK}
    cells = []
    for a in arena.get("attempts", []):
        action = _POLICY_TO_ACTION.get(a["policy"])
        if action is None:
            continue
        need, risk = meta.get(a["task"], ("unknown", "low"))
        cells.append(ControllerCell(context_need=need, risk_level=risk, provider_available=True,
                                    action=action, solved=a["solved"], cost=a["cost_usd"],
                                    conclusive=a["conclusive"]))
    search = TopologyControllerSearch().fit(cells)
    report = search.to_report(cells)
    out = ROOT / "reports" / "topology_controller_search.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"learned controller: {report['learned_controller_by_context_need']}")
    print(f"gain over static baseline: {report['controller_gain_over_static_baseline']} "
          f"promotable={report['promotable']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
