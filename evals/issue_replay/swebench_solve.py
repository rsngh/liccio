# ruff: noqa: E501
"""SWE-bench solving harness (P9 Pillar B) — drive a vendor CLI agent on a real repo, grade by tests.

A fair task gives the agent ONLY the repo @ base_commit (NOT the test_patch — the FAIL_TO_PASS tests
are held out) + the issue's problem_statement. The agent edits the repo natively (localize/multi-file/
iterate); we capture its `git diff`, STRIP any changes to test files (SWE-bench fairness: the agent must
fix code, not edit the graded tests), and grade the candidate diff with `swebench_adapter.verify`
against the prepared base+test_patch repo (named FAIL_TO_PASS / PASS_TO_PASS).

Vendor agents are subscription-metered ($0 here), so a saturation sweep + router comparison is cheap.

    uv run python -m evals.issue_replay.swebench_solve --agent gemini_cli --probe   # one fair task
    uv run python -m evals.issue_replay.swebench_solve --agent codex_cli \
        --slice reports/swebench_lite_slice.json --out reports/swebench_solve_codex.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from evals.issue_replay.swebench_adapter import (
    _CACHE,
    SweInstance,
    _sh,
    load_lite,
    prepare,
    verify,
)

_SOLVE_PROMPT = (
    "You are fixing a bug in this repository. Resolve the following issue by editing the source code "
    "(do NOT add or edit test files — only fix the library code). When done, leave the working tree "
    "with your fix applied.\n\nISSUE:\n{problem}\n"
)


def _solve_checkout(inst: SweInstance, agent: str, *, install_timeout: int = 480) -> tuple[Path, str] | None:
    """A base-commit checkout WITHOUT test_patch, in its own venv, for the agent to edit. Returns
    (repo_dir, venv_python) or None on failure. Scoped per (instance, agent) so concurrent agents on
    the same task don't clobber each other's working tree (the venv is shared — same deps)."""
    work = _CACHE / inst.instance_id
    repo = work / f"solve_{agent}"
    py = str(work / ".venv" / "bin" / "python")   # reuse the prepared venv (same deps)
    if (work / f".solve_{agent}_ready").exists() and repo.exists():
        _sh(["git", "reset", "--hard", "-q", "HEAD"], cwd=repo)
        _sh(["git", "clean", "-qfd"], cwd=repo)
        return repo, py
    if not Path(py).exists() and not prepare(inst, install_timeout=install_timeout).ok:
        return None          # ensure the env exists (prepare builds + installs it)
    if not repo.exists():
        rc, log = _sh(["git", "clone", "--quiet", f"https://github.com/{inst.repo}", str(repo)], timeout=300)
        if rc:
            return None
    _sh(["git", "checkout", "-q", "-f", inst.base_commit], cwd=repo)
    _sh(["git", "clean", "-qfdx", "-e", ".venv"], cwd=repo)
    _sh(["git", "-c", "user.email=acp@local", "-c", "user.name=acp", "commit", "-q",
         "--allow-empty", "-am", "base"], cwd=repo)
    (work / f".solve_{agent}_ready").write_text("ok")
    return repo, py


def _strip_test_changes(diff: str) -> str:
    """Drop hunks touching test files (fairness: the agent must fix code, not the graded tests)."""
    if not diff.strip():
        return diff
    out: list[str] = []
    keep = True
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            paths = line.split()
            keep = not any(("/test" in p or p.split("/")[-1].startswith("test_")
                            or p.endswith("_test.py") or "/tests/" in p) for p in paths[2:])
        if keep:
            out.append(line)
    return "".join(out)


def run_agent(inst: SweInstance, agent: str, *, timeout_s: int = 420) -> tuple[str, bool, float]:
    """Run the vendor CLI agent on a base checkout; return (candidate_diff, ran, wall_s)."""
    from acp.agents.vendor_native import VendorNativeHarness
    co = _solve_checkout(inst)
    if co is None:
        return "", False, 0.0
    repo, _py = co
    prompt = _SOLVE_PROMPT.format(problem=inst.problem_statement[:8000])
    t0 = time.monotonic()
    VendorNativeHarness(agent).run_task(repo, prompt, task_name=inst.instance_id, timeout_s=timeout_s)
    wall = round(time.monotonic() - t0, 1)
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=repo, capture_output=True, text=True, check=False).stdout
    return _strip_test_changes(diff), True, wall


def solve_and_grade(inst: SweInstance, agent: str, *, timeout_s: int = 420) -> dict:
    """Agent attempt + hidden grading (named FAIL_TO_PASS / gold-calibrated PASS_TO_PASS)."""
    diff, ran, wall = run_agent(inst, agent, timeout_s=timeout_s)
    prep = prepare(inst)
    if not prep.ok:
        return {"instance_id": inst.instance_id, "ran": ran, "solved": False, "note": "prep failed"}
    f2p, p2p = verify(prep, diff) if diff.strip() else (False, True)
    return {"instance_id": inst.instance_id, "family": inst.family, "agent": agent, "ran": ran,
            "produced_diff": bool(diff.strip()), "diff_lines": len(diff.splitlines()),
            "fail_to_pass": f2p, "pass_to_pass_kept": p2p, "solved": bool(f2p and p2p), "wall_s": wall}


def _fair_instances(slice_path: str) -> list[SweInstance]:
    fair_ids = {r["instance_id"] for r in json.loads(Path(slice_path).read_text())["per_task"] if r.get("fair")}
    return [i for i in load_lite(limit=0) if i.instance_id in fair_ids]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="gemini_cli", choices=["gemini_cli", "claude_code", "codex_cli"])
    ap.add_argument("--slice", default="reports/swebench_lite_slice.json")
    ap.add_argument("--out", default="")
    ap.add_argument("--probe", action="store_true", help="solve a single fair task and report")
    ap.add_argument("--timeout", type=int, default=420)
    args = ap.parse_args()
    insts = _fair_instances(args.slice)
    if args.probe:
        insts = insts[:1]
    print(f"solving {len(insts)} fair tasks with {args.agent}", flush=True)
    out = Path(args.out) if args.out else None
    rows: list = []
    done: set = set()
    if out and out.exists():
        rows = json.loads(out.read_text()).get("per_task", [])
        done = {r["instance_id"] for r in rows}
    for inst in insts:
        if inst.instance_id in done:
            continue
        r = solve_and_grade(inst, args.agent, timeout_s=args.timeout)
        rows.append(r)
        print(f"[{len(rows)}/{len(insts)}] {inst.instance_id:30} ran={r['ran']} diff={r.get('diff_lines',0)}L "
              f"F2P={r.get('fail_to_pass')} solved={r['solved']} ({r.get('wall_s',0)}s)", flush=True)
        if out:
            solved = sum(1 for x in rows if x["solved"])
            out.write_text(json.dumps({"experiment": "swebench_solve", "agent": args.agent,
                                       "n": len(rows), "solved": solved,
                                       "solve_rate": round(solved / len(rows), 3) if rows else 0.0,
                                       "per_task": rows}, indent=2) + "\n")
    solved = sum(1 for x in rows if x["solved"])
    print(f"\n=== {args.agent} === solved {solved}/{len(rows)} on the fair SWE-bench Lite slice", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
