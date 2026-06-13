# ruff: noqa: E501
"""Phase 0 — smallest experiment that proves or kills the verifier-guided-repair thesis.

Runs greedy verifier-guided repair (dense battery as the in-loop oracle, NEVER the hidden test) on the
11 diagnostic bundles: the 8 `no_progress` (right function, wrong fix) + 3 `solved` (regression guard).
Grades the finally-selected candidate ONCE with the hidden test (`verify`). Reports:

  * recovered / 8 no_progress  (the thesis: did a dense fair gradient flip bugs a binary oracle couldn't)
  * regression on the 3 solved
  * point-biserial r between battery score and hidden-pass over ALL scored candidates (value-function quality)
  * battery proxy precision/recall vs the hidden oracle, incl. gold-acceptance and buggy-rejection

KILL  : 0/8 recovered AND r < 0.2.    PROCEED: >= 2/8 recovered OR r >= 0.3.

    uv run python -m evals.issue_replay.guided_repair_phase0 --out reports/issue_replay_phase0_battery.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

from evals.issue_replay.guided_repair import guided_repair
from evals.issue_replay.replay_runner import verify
from evals.issue_replay.replay_task import IssueReplayTask

from acp.verification.repair_battery import build_battery, build_battery_v2, score_candidate

_MODEL = "gemini-3-flash-preview"
_RATE = (0.30e-6, 2.50e-6)


def _client():
    try:
        import anthropic
        return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ACP_ANTHROPIC_API_KEY"))
    except Exception:  # noqa: BLE001
        return None


def _select_targets(bundles: list[IssueReplayTask], diag_rows: list[dict]) -> list[tuple[str, IssueReplayTask]]:
    """Match each no_progress/solved diagnosis row to its v2 bundle by (module basename, issue prefix)."""
    targets: list[tuple[str, IssueReplayTask]] = []
    used: set[int] = set()
    for row in diag_rows:
        if row.get("category") not in ("no_progress", "solved"):
            continue
        mod, issue = row["module"], (row["issue"] or "")[:28]
        for i, b in enumerate(bundles):
            if i in used:
                continue
            if Path(b.module_path).name == mod and b.issue_title[:28] == issue:
                targets.append((row["category"], b))
                used.add(i)
                break
    return targets


def _point_biserial(scores: list[float], labels: list[int]) -> float:
    """Correlation between a continuous score and a binary outcome (hidden pass)."""
    n = len(scores)
    if n < 3 or len(set(labels)) < 2:
        return 0.0
    mean = sum(scores) / n
    sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / n)
    if sd == 0:
        return 0.0
    n1 = sum(labels)
    n0 = n - n1
    m1 = sum(s for s, y in zip(scores, labels, strict=True) if y) / n1
    m0 = sum(s for s, y in zip(scores, labels, strict=True) if not y) / n0
    return round(((m1 - m0) / sd) * math.sqrt(n1 * n0 / (n * n)), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="reports/real_issue_replay_full_v2.json")
    ap.add_argument("--diagnosis", default="reports/issue_replay_diagnosis.json")
    ap.add_argument("--out", default="reports/issue_replay_phase0_battery.json")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--model", default="gemini", help="in-loop repair model key (gemini|haiku|sonnet|opus)")
    ap.add_argument("--battery-v2", action="store_true",
                    help="use build_battery_v2 (fail-to-pass gate + AssertFlip + mutation weights)")
    ap.add_argument("--g1-only", action="store_true",
                    help="G1 gate: build batteries + score gold/buggy only — no repair LLM calls")
    ap.add_argument("--no-pbt", action="store_true",
                    help="ablation: disable the PBT/Hypothesis phase in build_battery_v2 (example-only)")
    ap.add_argument("--search-mode", default="greedy", choices=["greedy", "beam", "mcts"])
    ap.add_argument("--ladder", action="store_true",
                    help="enable in-loop model escalation (gemini->haiku->sonnet) on flat trajectories")
    ap.add_argument("--no-resume", action="store_true", help="ignore an existing --out and start fresh")
    args = ap.parse_args()

    from evals.issue_replay.run import _MODELS
    model_id, rate = _MODELS[args.model]
    bundles = [IssueReplayTask(**d) for d in json.loads(Path(args.corpus).read_text())]
    diag_rows = json.loads(Path(args.diagnosis).read_text())["rows"]
    targets = _select_targets(bundles, diag_rows)
    client = _client()
    if client is None:
        print("WARN: no Anthropic client (battery generation needs it) — set ANTHROPIC_API_KEY", flush=True)

    # RESUME (container reclamation on idle kills detached jobs ~2.4h in): reload prior per-bundle
    # rows and skip targets already done, so re-invoking accumulates instead of restarting.
    per_bundle: list = []
    done: set = set()
    if not args.no_resume and Path(args.out).exists():
        try:
            per_bundle = json.loads(Path(args.out).read_text()).get("per_bundle", [])
            done = {(r["module"], r["issue"]) for r in per_bundle}
            print(f"resume: {len(done)} bundles already done in {args.out}", flush=True)
        except Exception:  # noqa: BLE001
            per_bundle, done = [], set()

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for bi, (cat, b) in enumerate(targets):
            if (Path(b.module_path).name, b.issue_title[:50]) in done:
                continue
            # build the battery ONCE and reuse for the solve + the gold/buggy sanity (consistent labels)
            bench = root / f"bench{bi}"
            bench.mkdir(parents=True, exist_ok=True)
            from evals.issue_replay.guided_repair import _Spec
            spec = _Spec(f"{b.issue_title}\n{b.issue_body}", b.public_test, b.module_path)
            if args.battery_v2:
                from evals.issue_replay.repair_harness import _extract, _func_table, _localize
                table = _func_table(b.buggy)
                focus_names = _localize(b.buggy, b.issue_title, b.public_test, "")
                focus_src = _extract(b.buggy, focus_names, table) if focus_names else ""
                spans = [(table[n][0], table[n][1]) for n in focus_names if n in table] or None
                battery = build_battery_v2(spec, client=client, module_path=b.module_path,
                                           extra_files=b.extra_files, baseline_src=b.buggy,
                                           public_test=b.public_test, workspace_root=bench,
                                           focus_src=focus_src, focus_spans=spans,
                                           use_pbt=not args.no_pbt)
            else:
                battery = build_battery(spec, client=client, module_path=b.module_path,
                                        extra_files=b.extra_files, baseline_src=b.buggy,
                                        public_test=b.public_test, workspace_root=bench,
                                        n_example=8, n_property=4)
            if args.g1_only:
                gold_sc = score_candidate(battery, candidate_src=b.gold_patch, workspace_root=bench,
                                          candidate_id="gold")
                buggy_sc = score_candidate(battery, candidate_src=b.buggy, workspace_root=bench,
                                           candidate_id="buggy")
                row = {"category": cat, "module": Path(b.module_path).name, "issue": b.issue_title[:50],
                       "battery_valid": battery.valid, "invalid_reason": battery.invalid_reason,
                       "n_checks": len(battery.checks), "n_discriminating": battery.n_discriminating,
                       "n_guard": battery.n_guard, "check_kinds": [k for k, _ in battery.checks],
                       "mutation_info": {k: v for k, v in battery.mutation_info.items() if k != "flips"},
                       "gold_score": gold_sc.score, "gold_accept": gold_sc.accept(),
                       "gold_disc_frac": gold_sc.disc_frac, "gold_guard_frac": gold_sc.guard_frac,
                       "buggy_score": buggy_sc.score, "buggy_accept": buggy_sc.accept(),
                       "gen_cost_usd": battery.gen_cost_usd}
                per_bundle.append(row)
                print(f"[{len(per_bundle)}/{len(targets)}] {cat:11} {row['module']:14} valid={row['battery_valid']} "
                      f"disc={row['n_discriminating']} gold_accept={row['gold_accept']} "
                      f"gold_score={row['gold_score']} buggy_accept={row['buggy_accept']}", flush=True)
                _persist_g1(args.out, per_bundle, len(targets))
                continue
            res = guided_repair(b, root / f"gr{bi}", model_id=model_id, rate=rate, client=client,
                                search_mode=args.search_mode, k=args.k, rounds=args.rounds,
                                ladder=args.ladder, battery=battery, record_candidates=True)
            hidden_pass, _public = verify(b, root / f"ver{bi}", module_src=res.module_src)
            gold_sc = score_candidate(battery, candidate_src=b.gold_patch, workspace_root=bench,
                                      candidate_id="gold") if battery.checks else None
            buggy_sc = score_candidate(battery, candidate_src=b.buggy, workspace_root=bench,
                                       candidate_id="buggy") if battery.checks else None
            per_bundle.append({
                "category": cat, "repo": b.repo_name.split("/")[-1], "module": Path(b.module_path).name,
                "issue": b.issue_title[:50], "hidden_pass": hidden_pass,
                "best_score": res.telemetry["best_score"], "best_proxy_pass": res.telemetry["best_proxy_pass"],
                "score_trajectory": res.telemetry["score_trajectory"],
                "n_checks": res.telemetry["n_checks"], "n_discriminating": res.telemetry["n_discriminating"],
                "gold_proxy_pass": (gold_sc.proxy_pass if gold_sc else None),
                "gold_score": (gold_sc.score if gold_sc else None),
                "gold_accept": (gold_sc.accept() if gold_sc else None),
                "buggy_proxy_pass": (buggy_sc.proxy_pass if buggy_sc else None),
                # battery false positive: search satisfied the proxy (accept) but the hidden test fails
                "battery_false_positive": bool(res.telemetry.get("best_accept") and not hidden_pass),
                "focus_names": res.telemetry.get("focus_names"),
                "class_mode": res.telemetry.get("class_mode"),
                "battery_valid": res.telemetry.get("battery_valid"),
                "best_accept": res.telemetry.get("best_accept"),
                "escalations": res.telemetry.get("escalations", []),
                "cost_usd": res.cost_usd})
            print(f"[{len(per_bundle)}/{len(targets)}] {cat:11} {Path(b.module_path).name:14} hidden_pass={hidden_pass} "
                  f"best_score={res.telemetry['best_score']} traj={res.telemetry['score_trajectory']}", flush=True)
            _persist(args.out, per_bundle, targets)

    if args.g1_only:
        n = len(per_bundle)
        nv = sum(1 for r_ in per_bundle if r_["battery_valid"])
        ga_ = sum(1 for r_ in per_bundle if r_["gold_accept"])
        br_ = sum(1 for r_ in per_bundle if not r_["buggy_accept"])
        stuck = sum(1 for r_ in per_bundle if r_["gold_score"] <= 0.41)
        g1 = nv >= 9 and ga_ >= 9 and br_ == n and stuck == 0
        print(f"\n=== G1 === valid {nv}/{n} | gold_accept {ga_}/{n} | buggy_rejected {br_}/{n} | "
              f"gold_stuck_at_0.4 {stuck} | GATE {'PASS' if g1 else 'FAIL'}", flush=True)
        return 0
    m = _metrics(per_bundle)
    print(f"\n=== PHASE 0 === recovered {m['recovered_no_progress']}/{m['n_no_progress']} no_progress | "
          f"regressed {m['regressed_solved']}/{m['n_solved']} solved | battery_false_positives "
          f"{m['battery_false_positives']} | score<->hidden r={m['score_vs_hidden_point_biserial']} | "
          f"decision={m['decision']}", flush=True)
    return 0


def _persist_g1(out, per_bundle, n_targets):
    n = len(per_bundle)
    nv = sum(1 for r in per_bundle if r["battery_valid"])
    ga = sum(1 for r in per_bundle if r["gold_accept"])
    br = sum(1 for r in per_bundle if not r["buggy_accept"])
    stuck = sum(1 for r in per_bundle if r["gold_score"] <= 0.41)
    rep = {
        "experiment": "issue_replay_p7_g1_battery_v2",
        "gate": "valid>=9/11 AND gold_accept>=9/11 AND buggy_rejected==11/11 AND no gold stuck at 0.4",
        "n_done": n, "n_targets": n_targets,
        "valid": nv, "gold_accept": ga, "buggy_rejected": br, "gold_stuck_at_0.4": stuck,
        "gate_pass": bool(nv >= 9 and ga >= 9 and br == n and stuck == 0 and n == n_targets),
        "total_gen_cost_usd": round(sum(r["gen_cost_usd"] for r in per_bundle), 4),
        "per_bundle": per_bundle,
        "evidence_tier": "live: battery-v2 (fail-to-pass gate + AssertFlip + mutation weights); gold/buggy scored only — no repair calls",
    }
    Path(out).write_text(json.dumps(rep, indent=2) + "\n")


def _metrics(per_bundle: list) -> dict:
    """All headline metrics derived from the persisted per-bundle rows (resume-safe)."""
    np_rows = [r for r in per_bundle if r["category"] == "no_progress"]
    solved_rows = [r for r in per_bundle if r["category"] == "solved"]
    recovered = sum(1 for r in np_rows if r["hidden_pass"])
    regressed = sum(1 for r in solved_rows if not r["hidden_pass"])
    fps = sum(1 for r in per_bundle if r.get("battery_false_positive"))
    scores = [r["best_score"] for r in per_bundle if r.get("best_score") is not None]
    labels = [int(r["hidden_pass"]) for r in per_bundle if r.get("best_score") is not None]
    r = _point_biserial(scores, labels)
    valid = sum(1 for r in per_bundle if r.get("battery_valid"))
    return {"recovered_no_progress": recovered, "n_no_progress": len(np_rows),
            "regressed_solved": regressed, "n_solved": len(solved_rows),
            "battery_false_positives": fps, "battery_valid": valid,
            "score_vs_hidden_point_biserial": r,
            "decision": ("PROCEED" if (recovered >= 2 or r >= 0.3)
                         else "KILL" if (recovered == 0 and r < 0.2) else "INCONCLUSIVE")}


def _persist(out, per_bundle, targets):
    m = _metrics(per_bundle)
    rep = {
        "experiment": "issue_replay_p7_guided_battery_v2",
        "thesis": "a discriminating-by-construction battery + search recovers no_progress bugs the binary loop could not",
        "n_targets": len(targets), "n_done": len(per_bundle),
        **m,
        "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in per_bundle), 4),
        "per_bundle": per_bundle,
        "evidence_tier": "live: battery-v2 in-loop oracle (spec+public+buggy only); search per --search-mode; hidden test for grading only",
    }
    Path(out).write_text(json.dumps(rep, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
