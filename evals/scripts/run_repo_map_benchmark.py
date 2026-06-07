"""Benchmark: graph-ranked repo map vs chunk retrieval — API coverage per token.

Research basis (`pdfs/memory and context/aider-graph-map.pdf`): a concise, graph-ranked map of
the whole repo's signatures gives a coding agent breadth ("APIs from everywhere") at a fraction
of the tokens that full-body chunk retrieval costs. This deterministic benchmark quantifies that
on a synthetic repo of N API modules: at a fixed token budget, how many distinct API signatures
does each strategy expose? Writes evals/reports/repo_map_coverage.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from acp.context.compiler import ContextCompiler
from acp.schemas.task import Task

N_MODULES = 40
BUDGETS = (200, 400, 800, 1600)
STRATEGIES = ("minimal", "hybrid_keyword_embedding", "repo_map")


def _build_repo(root: Path) -> list[str]:
    names = []
    for i in range(N_MODULES):
        nm = f"service_{i}_handler"
        names.append(nm)
        body = "\n".join(f"    step_{j} = {j} * {i}" for j in range(12))
        (root / f"svc_{i}.py").write_text(f"def {nm}(payload):\n{body}\n    return payload\n")
    return names


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        names = _build_repo(root)
        task = Task(repo_id="r", title="wire the services", body="connect the service handlers")
        for budget in BUDGETS:
            row = {"token_budget": budget}
            for strat in STRATEGIES:
                pack = ContextCompiler(str(root), "r", "s").compile(
                    task, strategy=strat, token_budget=budget)
                txt = "\n".join(it.content for it in pack.items)
                covered = sum(1 for n in names if f"def {n}" in txt)
                row[strat] = {"apis_covered": covered, "of": N_MODULES,
                              "pack_tokens": pack.token_estimate}
            rows.append(row)
            rm = row["repo_map"]["apis_covered"]
            hy = row["hybrid_keyword_embedding"]["apis_covered"]
            print(f"budget={budget:5d}  repo_map={rm:2d}/{N_MODULES}  "
                  f"hybrid={hy:2d}/{N_MODULES}  lift={rm - hy:+d}")
    # the headline: repo map's coverage advantage at the tightest budget
    tight = rows[0]
    report = {
        "experiment": "repo_map_coverage",
        "research": "aider repo map (graph-ranked signatures) — breadth per token",
        "n_modules": N_MODULES,
        "coverage_by_budget": rows,
        "headline": {
            "budget": tight["token_budget"],
            "repo_map_apis": tight["repo_map"]["apis_covered"],
            "hybrid_apis": tight["hybrid_keyword_embedding"]["apis_covered"],
            "coverage_multiple": round(
                tight["repo_map"]["apis_covered"]
                / max(tight["hybrid_keyword_embedding"]["apis_covered"], 1), 2),
        },
        "deterministic": True,
    }
    out = Path("evals/reports/repo_map_coverage.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nheadline: at budget={report['headline']['budget']}, repo_map covers "
          f"{report['headline']['repo_map_apis']} APIs vs hybrid "
          f"{report['headline']['hybrid_apis']} "
          f"({report['headline']['coverage_multiple']}x)\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
