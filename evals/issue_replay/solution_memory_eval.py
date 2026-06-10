# ruff: noqa: E501
"""Solution-memory payoff — does cached-fix REPLAY reproduce a verified solve, and what does it save?

Validates #3 end-to-end on REAL bundles, fully offline and fast (no agent calls): for each bundle,
take the GOLD fix as the "previously-verified solution", store its changed function(s) in the
SolutionStore, then on a RECURRENCE replay it (AST-splice into the buggy module) and run the pristine
held-out test. Measures:

  * replay_success_rate — how often splice+verify reproduces a passing fix (the cache-hit path works);
  * workload cost model — at recurrence rate r, fraction of ladder cost avoided (recurrences solved
    at ~$0 instead of paying the escalation ladder).

This is the realistic deployment payoff: repeated/regressed bugs on one codebase become free solves.

    uv run python -m evals.issue_replay.solution_memory_eval --out reports/issue_replay_solution_memory.json
"""

from __future__ import annotations

import argparse
import ast
import json
import tempfile
from pathlib import Path

from evals.issue_replay.replay_runner import verify
from evals.issue_replay.replay_task import IssueReplayTask

from acp.memory.solution_store import SolutionStore, signature_of


def _func_srcs(src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            s = min([node.lineno, *[d.lineno for d in node.decorator_list]])
            out[node.name] = "\n".join(lines[s - 1:node.end_lineno or node.lineno])
    return out


def changed_functions(buggy: str, gold: str) -> tuple[str, ...]:
    """Function names whose source differs between buggy and gold (the fix's footprint)."""
    b, g = _func_srcs(buggy), _func_srcs(gold)
    return tuple(n for n, src in g.items() if b.get(n) != src)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle-files", nargs="+",
                    default=["reports/real_issue_replay_full.json"])
    ap.add_argument("--out", default="reports/issue_replay_solution_memory.json")
    args = ap.parse_args()
    bundles: list[IssueReplayTask] = []
    for f in args.bundle_files:
        if Path(f).exists():
            bundles += [IssueReplayTask(**d) for d in json.loads(Path(f).read_text())]
    per_bundle = []
    replay_ok = 0
    with tempfile.TemporaryDirectory(prefix="solmem_") as d:
        root = Path(d)
        for bi, b in enumerate(bundles):
            fns = changed_functions(b.buggy, b.gold_patch)
            store = SolutionStore()
            sig = signature_of("AssertionError", fns[0] if fns else "")
            stored = store.record(repo_family=b.repo_name, failure_signature=sig,
                                  module_path=b.module_path, fixed_module_src=b.gold_patch,
                                  function_names=fns, buggy_module_src=b.buggy, verified=True)
            cand = store.replay(tenant="tenant_a", repo_family=b.repo_name, failure_signature=sig,
                                buggy_module_src=b.buggy) if stored else None
            solved = False
            if cand is not None:
                hidden, _ = verify(b, root / f"b{bi}", module_src=cand)
                solved = bool(hidden)
            replay_ok += int(solved)
            per_bundle.append({"repo": b.repo_name, "module": b.module_path,
                               "changed_fns": list(fns), "stored": stored, "replay_solved": solved})
    n = len(bundles)
    rate = replay_ok / n if n else 0.0
    # workload cost model: first occurrence pays the ladder (normalize to 1.0); a recurrence that
    # replays-successfully costs ~0. At recurrence fraction r, avoided cost = r * replay_success_rate.
    cost_model = {f"recurrence_{int(r*100)}pct": round(r * rate, 3) for r in (0.25, 0.5, 0.75)}
    rep = {
        "experiment": "issue_replay_solution_memory",
        "question": "does cached-fix replay reproduce a verified solve, and how much ladder cost does it avoid on recurrences?",
        "n_bundles": n, "replay_success": replay_ok, "replay_success_rate": round(rate, 3),
        "fraction_of_ladder_cost_avoided_at_recurrence": cost_model,
        "evidence_tier": "offline; gold fix stored then AST-splice-replayed into the buggy module, graded by the pristine held-out test; zero agent calls",
        "per_bundle": per_bundle,
    }
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== SOLUTION MEMORY (n={n}) === replay reproduces verified solve {replay_ok}/{n} = {rate:.0%}")
    print(f"ladder cost avoided: at 50% recurrence -> {cost_model['recurrence_50pct']:.0%} of total workload cost")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
