# ruff: noqa: E501
"""LIVE escalation ladder with failure-brief handoff (Prong B of the pdfs/ research synthesis).

The offline economics (issue_replay_routing_economics*.json) replayed per-agent results; this runs
the ladder FOR REAL: inproc repair_v2 -> gemini_cli -> claude_code -> codex_cli with verify-stop.
The new mechanism — from MAR (2512.10696), committee-boosting (2605.14163) and the SDB shared-artifact
contract (2605.20173) — is DIAGNOSIS HANDOFF: when rung i fails, its attempt is distilled into a
compact failure brief (capped diff of what it tried + the test failure it died on) and injected into
rung i+1's prompt. Independent attempts become a relay: each agent starts from the previous one's
post-mortem instead of from scratch.

Measured against the no-hint per-agent vectors we already hold, this answers two questions:
  1. Does the live ladder reproduce the offline verify-stop economics (stop-rung distribution)?
  2. Do hints flip bundles an agent missed when running independently (union lift / earlier stops)?

Grading unchanged: pristine held-out test on the produced module; agents cannot edit the oracle.

    uv run python -m evals.issue_replay.ladder_live --bundle-file reports/real_issue_replay_full_hard.json \
        --limit 10 --out reports/issue_replay_ladder_live_hard.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import time
from pathlib import Path

from evals.issue_replay.replay_runner import verify
from evals.issue_replay.replay_task import IssueReplayTask

RUNGS = ("inproc_repair2", "gemini_cli", "claude_code", "codex_cli")


def _brief(rung: str, buggy: str, attempt: str, failure: str, *, cap: int = 40) -> str:
    diff = list(difflib.unified_diff(buggy.splitlines(), attempt.splitlines(), lineterm="", n=1))[2:]
    dtxt = "\n".join(diff[:cap]) or "(the attempt made no change)"
    return (f"[{rung}] attempted patch (unified diff, capped):\n{dtxt}\n\n"
            f"[{rung}] test failure after its patch:\n{failure[:1200]}")


def _attempt(rung: str, task: IssueReplayTask, root: Path, hint: str) -> tuple[str, float]:
    if rung == "inproc_repair2":
        from evals.issue_replay.repair_v2 import repair_v2
        from evals.issue_replay.run import _MODELS
        produced, cost, _ = repair_v2(task, root, model_id=_MODELS["gemini"][0],
                                      rate=_MODELS["gemini"][1])
        return produced, cost
    from evals.issue_replay.run import _produce_vendor
    produced, cost, _ = _produce_vendor(task, rung, root, hint=hint)
    return produced, cost


def run_ladder(bundles: list[IssueReplayTask], *, hints: bool = True) -> dict:
    per_bundle = []
    stop_rung: dict[str, int] = dict.fromkeys([*RUNGS, "unsolved"], 0)
    t0 = time.time()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ladder_live_") as d:
        root = Path(d)
        for bi, b in enumerate(bundles):
            hint = ""
            path: list[dict] = []
            solved_at = "unsolved"
            for rung in RUNGS:
                t1 = time.time()
                produced, cost = _attempt(rung, b, root / f"b{bi}_{rung}", hint)
                hidden, public = verify(b, root / f"v{bi}_{rung}", module_src=produced)
                path.append({"rung": rung, "hidden_pass": hidden, "public_pass": public,
                             "cost_usd": round(cost, 6), "hinted": bool(hint),
                             "elapsed_s": round(time.time() - t1, 1)})
                print(f"[{b.repo_name} #{bi}] {rung} hidden={hidden} hinted={bool(hint)} "
                      f"({path[-1]['elapsed_s']}s)", flush=True)
                if hidden:
                    solved_at = rung
                    break
                if hints:
                    # distill this rung's post-mortem for the next rung (diagnosis handoff)
                    from evals.issue_replay.repair_harness import _run

                    from acp.routing.reflective_repair import failure_summary
                    work = root / f"f{bi}_{rung}"
                    work.mkdir(parents=True, exist_ok=True)
                    for p, c in b.extra_files.items():
                        (work / p).parent.mkdir(parents=True, exist_ok=True)
                        (work / p).write_text(c)
                    (work / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
                    (work / "test_repro.py").write_text(b.hidden_test)
                    (work / b.module_path).parent.mkdir(parents=True, exist_ok=True)
                    (work / b.module_path).write_text(produced)
                    _, out = _run(work, "test_repro.py")
                    hint = _brief(rung, b.buggy, produced, failure_summary(out))
            stop_rung[solved_at] += 1
            per_bundle.append({"repo": b.repo_name, "issue": b.issue_title[:70],
                               "solved_at": solved_at, "path": path})
    n = len(bundles)
    solved = n - stop_rung["unsolved"]
    return {
        "experiment": "issue_replay_ladder_live",
        "question": "does the live verify-stop ladder with diagnosis handoff match offline economics and lift the union?",
        "hints": hints, "n_bundles": n, "solved": solved, "rate": round(solved / n, 3),
        "stop_rung": stop_rung, "elapsed_s": round(time.time() - t0, 1),
        "evidence_tier": "live escalation; pristine held-out test as verify-stop; hints carry only "
                         "prior FAILED attempt diff + test output (no gold, no oracle leakage)",
        "per_bundle": per_bundle,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle-file", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-hints", action="store_true", help="ablation: plain relay without handoff")
    ap.add_argument("--out", default="reports/issue_replay_ladder_live.json")
    args = ap.parse_args()
    bundles = [IssueReplayTask(**d) for d in json.loads(Path(args.bundle_file).read_text())]
    if args.limit:
        bundles = bundles[:args.limit]
    rep = run_ladder(bundles, hints=not args.no_hints)
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== LADDER LIVE (hints={rep['hints']}) === solved {rep['solved']}/{rep['n_bundles']} "
          f"stop-rung {rep['stop_rung']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
