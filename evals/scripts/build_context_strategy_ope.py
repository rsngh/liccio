"""Build the context-strategy OPE report from the latest arena run (GOALS Alpha 42 P4).

Deterministic: joins arena attempts with each task's context_need, maps policies to context
strategies (cheap_single->minimal, repo_map_router->repo_map), and estimates which strategy to
route per context_need by verified success per dollar. Writes reports/context_strategy_ope.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from acp.context.context_strategy_ope import ContextStrategyOPE  # noqa: E402

_POLICY_TO_STRATEGY = {"cheap_single": "minimal", "repo_map_router": "repo_map"}


def main() -> int:
    arena_path = ROOT / "reports" / "metarouter_arena.json"
    if not arena_path.exists():
        print(f"[skip] {arena_path} not found — run the arena first")
        return 0
    arena = json.loads(arena_path.read_text())
    need_by_task = {}
    # task context_need lives in the task pack; recover it from per_task ordering via attempts
    from evals.metarouter_arena.task_pack import TASK_PACK
    need_by_task = {t.name: t.context_need for t in TASK_PACK}
    cells = []
    for a in arena.get("attempts", []):
        strat = _POLICY_TO_STRATEGY.get(a["policy"])
        if strat is None:
            continue
        cells.append({"context_need": need_by_task.get(a["task"], "unknown"), "strategy": strat,
                      "solved": a["solved"], "cost_usd": a["cost_usd"],
                      "conclusive": a["conclusive"]})
    report = ContextStrategyOPE(min_samples=1).fit(cells).to_report()
    out = ROOT / "reports" / "context_strategy_ope.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    for need, rec in report["recommendations"].items():
        print(f"  {need:18s} -> {rec.get('recommended')}")
    print(f"grep_vs_embedding: {report['grep_vs_embedding']['verdict']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
