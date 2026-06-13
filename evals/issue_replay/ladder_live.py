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


def _unified(buggy: str, produced: str) -> str:
    return "".join(difflib.unified_diff(buggy.splitlines(keepends=True),
                                        produced.splitlines(keepends=True), "buggy", "proposed"))


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


def _spec_focus(b: IssueReplayTask):
    """(spec, focus_src, focus_spans) for a bundle — reuses the localize/extract path (fair: spec +
    public test + buggy focus only, never the hidden test)."""
    from evals.issue_replay.guided_repair import _Spec
    from evals.issue_replay.repair_harness import _extract, _func_table, _localize
    tbl = _func_table(b.buggy)
    fn = _localize(b.buggy, b.issue_title, b.public_test, "")
    focus = _extract(b.buggy, fn, tbl) if fn else ""
    spans = [(tbl[n][0], tbl[n][1]) for n in fn if n in tbl] or None
    spec = _Spec(f"{b.issue_title}\n{b.issue_body}", b.public_test, b.module_path)
    return spec, focus, spans


def run_ladder(bundles: list[IssueReplayTask], *, hints: bool = True, out: Path | None = None,
               referee: bool = False, client=None) -> dict:
    per_bundle = []
    stop_rung: dict[str, int] = dict.fromkeys([*RUNGS, "unsolved"], 0)
    t0 = time.time()
    import tempfile

    def snapshot() -> dict:
        done = len(per_bundle)
        # FAIR-STOP accounting (referee mode): the referee decides commit; the hidden test only GRADES.
        committed = [r for r in per_bundle if r.get("committed_rung")]
        false_commit = sum(1 for r in committed if not r.get("commit_hidden_pass"))
        # missed = a rung produced a hidden-passing fix but the referee never committed it (lost solve)
        missed = sum(1 for r in per_bundle if not r.get("committed_rung")
                     and any(p.get("hidden_pass") for p in r["path"]))
        solved_fair = sum(1 for r in committed if r.get("commit_hidden_pass"))
        rep = {"experiment": "issue_replay_ladder_referee" if referee else "issue_replay_ladder_live",
                "question": ("does the live ladder with the AUTO-REFEREE as the FAIR stop-signal solve at "
                             "low cost with a bounded false-commit rate (hidden test = offline grader only)?"
                             if referee else
                             "does the live verify-stop ladder with diagnosis handoff match offline economics and lift the union?"),
                "hints": hints, "fair_stop_referee": referee, "n_bundles": len(bundles), "completed": done,
                "stop_rung": stop_rung, "elapsed_s": round(time.time() - t0, 1),
                "evidence_tier": ("live escalation; AUTO-REFEREE (mutation-validated battery + debate) as the FAIR stop; "
                                  "hidden test used ONLY to grade commits (false-commit/missed), never to decide the stop"
                                  if referee else
                                  "live escalation; pristine held-out test as verify-stop; hints carry only prior FAILED attempt diff + test output (no gold, no oracle leakage)"),
                "per_bundle": per_bundle}
        if referee:
            rep["solved"] = solved_fair
            rep["committed"] = len(committed)
            rep["false_commit"] = false_commit
            rep["false_commit_rate"] = round(false_commit / len(committed), 3) if committed else 0.0
            rep["missed"] = missed
        else:
            rep["solved"] = done - stop_rung["unsolved"]
        return rep

    with tempfile.TemporaryDirectory(prefix="ladder_live_") as d:
        root = Path(d)
        for bi, b in enumerate(bundles):
            hint = ""
            path: list[dict] = []
            solved_at = "unsolved"
            bat = spec = None
            committed_rung = None
            commit_hidden = False
            if referee:
                from acp.verification.repair_battery import build_battery_v2
                spec, focus, spans = _spec_focus(b)
                bat = build_battery_v2(spec, client=client, module_path=b.module_path,
                                       extra_files=b.extra_files, baseline_src=b.buggy,
                                       public_test=b.public_test, workspace_root=root / f"bat{bi}",
                                       focus_src=focus, focus_spans=spans)
            for rung in RUNGS:
                t1 = time.time()
                produced, cost = _attempt(rung, b, root / f"b{bi}_{rung}", hint)
                hidden, public = verify(b, root / f"v{bi}_{rung}", module_src=produced)  # GRADER only in referee mode
                row = {"rung": rung, "hidden_pass": hidden, "public_pass": public,
                       "cost_usd": round(cost, 6), "hinted": bool(hint),
                       "elapsed_s": round(time.time() - t1, 1)}
                stop = hidden
                if referee:
                    from acp.verification.auto_referee import referee as _referee
                    rv = _referee(bat, produced, workspace_root=root / f"rv{bi}_{rung}",
                                  candidate_id=f"{bi}_{rung}", diff=_unified(b.buggy, produced),
                                  client=client, spec=spec)
                    stop = rv.accept
                    row["referee_accept"] = rv.accept
                    row["referee_reason"] = rv.reason[:120]
                    row["mutation_validated"] = rv.mutation_validated
                path.append(row)
                print(f"[{b.repo_name} #{bi}] {rung} hidden={hidden} "
                      f"{'referee=' + str(row.get('referee_accept')) + ' ' if referee else ''}hinted={bool(hint)} "
                      f"({row['elapsed_s']}s)", flush=True)
                if stop:
                    solved_at = rung
                    if referee:
                        committed_rung, commit_hidden = rung, hidden
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
                    _, fail_out = _run(work, "test_repro.py")  # don't shadow the `out` report Path
                    hint = _brief(rung, b.buggy, produced, failure_summary(fail_out))
            stop_rung[solved_at] += 1
            per_bundle.append({"repo": b.repo_name, "issue": b.issue_title[:70],
                               "solved_at": solved_at, "path": path,
                               "committed_rung": committed_rung,
                               "commit_hidden_pass": commit_hidden,
                               "battery_valid": (bat.valid if bat is not None else None),
                               "n_discriminating": (bat.n_discriminating if bat is not None else None)})
            if out is not None:           # incremental persist: a late crash never wipes prior bundles
                out.write_text(json.dumps(snapshot(), indent=2) + "\n")
    n = len(bundles)
    rep = snapshot()
    rep["rate"] = round((n - stop_rung["unsolved"]) / n, 3)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle-file", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-hints", action="store_true", help="ablation: plain relay without handoff")
    ap.add_argument("--referee", action="store_true",
                    help="use the AUTO-REFEREE as the FAIR stop-signal (hidden test = offline grader only)")
    ap.add_argument("--out", default="reports/issue_replay_ladder_live.json")
    args = ap.parse_args()
    bundles = [IssueReplayTask(**d) for d in json.loads(Path(args.bundle_file).read_text())]
    if args.limit:
        bundles = bundles[:args.limit]
    client = None
    if args.referee:
        from evals.issue_replay.guided_repair_phase0 import _client
        client = _client()
    rep = run_ladder(bundles, hints=not args.no_hints, out=Path(args.out),
                     referee=args.referee, client=client)
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    if rep.get("fair_stop_referee"):
        print(f"\n=== LADDER REFEREE === solved {rep['solved']}/{rep['n_bundles']} | committed {rep['committed']} | "
              f"false-commit {rep['false_commit']} (rate {rep['false_commit_rate']}) | missed {rep['missed']} | "
              f"stop-rung {rep['stop_rung']}")
    else:
        print(f"\n=== LADDER LIVE (hints={rep['hints']}) === solved {rep['solved']}/{rep['n_bundles']} "
              f"stop-rung {rep['stop_rung']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
