# ruff: noqa: E501
"""Failure diagnostic for the real issue-replay corpus (GOALS P3).

Five configurations all plateaued at 3/17 on the real bundles. Before spending budget scaling the
corpus, this answers WHY the other 14 fail — cheaply. For each bundle it:

  1. (free) measures the ORACLE GAP: which tests in the held-out file the buggy base fails and the
     gold fix flips — i.e. how broad a fix the oracle demands (1 test = a clean single-bug; many,
     spanning many functions = the test file demands more than a one-function edit).
  2. (cheap) re-runs the enhanced repair harness (gemini) and classifies the produced module's
     remaining failures vs the buggy baseline:
       solved        — produced passes the whole file
       no_progress   — same tests fail as the buggy base (wrong region / wrong fix)
       partial       — fixed some target tests but not all, broke nothing new
       regressed     — introduced NEW failures the buggy base didn't have

This separates "localization/capability" failures from "oracle too broad" failures, and tells us
whether the problem is solvable-in-principle before a big run.

    uv run python -m evals.issue_replay.diagnose --out reports/issue_replay_diagnosis.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from evals.issue_replay.repair_harness import _localize, repair_one
from evals.issue_replay.replay_task import IssueReplayTask

_MODEL = ("gemini-3-flash-preview", (0.30e-6, 2.50e-6))


def _failed_set(module_src: str, task: IssueReplayTask, root: Path) -> tuple[set[str], int, bool, bool]:
    """Run the held-out test file against module_src.

    Returns (failed_test_names, total_tests, passed, errored). ``passed`` is authoritative from the
    return code (matches the real grader); ``errored`` flags a collection error / timeout where no
    per-test results were produced (so "no FAILED line" must NOT be read as a pass)."""
    repo = root / f"d_{abs(hash(module_src)) % 10**9}"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / task.module_path).write_text(module_src)
    for p, c in task.extra_files.items():
        (repo / p).write_text(c)
    (repo / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
    (repo / "test_h.py").write_text(task.hidden_test)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(["python", "-m", "pytest", "test_h.py", "-v", "-p", "no:cacheprovider",
                               "-o", "addopts="], cwd=repo, capture_output=True, text=True,
                              timeout=120, check=False, env=env)
        out, rc = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return set(), 0, False, True
    failed = set(re.findall(r"::(\w+)\s+FAILED", out)) | set(re.findall(r"(\w+)\s+FAILED", out))
    total = len(re.findall(r"::\w+\s+(?:PASSED|FAILED)", out))
    passed = rc == 0
    errored = (not passed) and (not failed) and ("error" in out.lower())
    return failed, total, passed, errored


def diagnose(bundles: list[IssueReplayTask]) -> dict:
    rows = []
    cats: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="diag_") as d:
        root = Path(d)
        for b in bundles:
            buggy_fail, total, buggy_pass, buggy_err = _failed_set(b.buggy, b, root)
            gold_fail, _, gold_pass, _ = _failed_set(b.gold_patch, b, root)
            focus = _localize(b.buggy, b.issue_title, b.hidden_test, "")
            produced, cost, ran = repair_one(b, root, model_id=_MODEL[0], rate=_MODEL[1], k=2)
            prod_fail, _, prod_pass, prod_err = _failed_set(produced, b, root)
            fixed = buggy_fail - prod_fail
            new_break = prod_fail - buggy_fail
            # authoritative pass/fail is the return code (matches the real grader)
            if buggy_err or prod_err or total == 0:
                cat = "unmeasurable"          # test file timed out / errored standalone — exclude
            elif prod_pass:
                cat = "solved"
            elif new_break:
                cat = "regressed"             # model broke tests the buggy base passed
            elif fixed:
                cat = "partial"               # fixed some target tests, not all
            else:
                cat = "no_progress"           # same tests still fail: wrong fix (or wrong region)
            cats[cat] = cats.get(cat, 0) + 1
            rows.append({
                "repo": b.repo_name, "module": b.module_path, "issue": b.issue_title[:60],
                "tests_total": total, "oracle_gap": len(buggy_fail), "gold_passes": gold_pass,
                "focus": focus, "localized": bool(focus), "produced_passes": prod_pass,
                "fixed": len(fixed), "newly_broken": len(new_break),
                "category": cat, "cost_usd": round(cost, 6),
            })
            print(f"[{cat:12}] {b.module_path:13} gap={len(buggy_fail):2} focus={focus} "
                  f"prod_pass={prod_pass} fixed={len(fixed)} new_break={len(new_break)}", flush=True)
    measurable = [r for r in rows if r["category"] != "unmeasurable"]
    gaps = [r["oracle_gap"] for r in measurable] or [0]
    return {
        "experiment": "issue_replay_diagnosis",
        "n": len(rows),
        "n_measurable": len(measurable),
        "categories": cats,
        "solved_of_measurable": f"{cats.get('solved', 0)}/{len(measurable)}",
        "localized_count": sum(1 for r in rows if r["localized"]),
        "oracle_gap_over_measurable": {
            "min": min(gaps), "max": max(gaps), "median": sorted(gaps)[len(gaps) // 2],
            "single_test_bugs": sum(1 for g in gaps if g == 1),
            "broad_bugs_gt3": sum(1 for g in gaps if g > 3)},
        "gold_passes_all_measurable": all(r["gold_passes"] for r in measurable),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/issue_replay_diagnosis.json")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    full = Path("reports/real_issue_replay_full.json")
    bundles = [IssueReplayTask(**x) for x in json.loads(full.read_text())]
    rep = diagnose(bundles)
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print("\n=== DIAGNOSIS ===")
    print("categories:", rep["categories"])
    print("solved/measurable:", rep["solved_of_measurable"],
          "| gold passes all measurable:", rep["gold_passes_all_measurable"],
          "| localized:", rep["localized_count"], "/", rep["n"])
    print("oracle gap (measurable):", rep["oracle_gap_over_measurable"])
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
