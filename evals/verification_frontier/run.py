# ruff: noqa: E501
"""Increment 4 (frontier) — self-evolving repo playbook + calibrated stop for non-test tasks.

Two deterministic measurements:
  A) PLAYBOOK (ACE 2510.04618 / AGENTS.md 2602.11988): over sessions the router distils verified
     fixes into a per-repo playbook; we measure that the playbook accumulates the RIGHT lessons and
     surfaces the signature-relevant one first (coverage + precision of the evolved context).
  B) CALIBRATED STOP (Sufficient Context 2411.06037): for tasks with no runnable test, the stop
     signal is a calibrated confidence + abstention; we measure that it trades coverage for PRECISION
     — it never commits a wrong answer (no confident-but-wrong auto-commit), abstaining instead.

    uv run python -m evals.verification_frontier.run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from acp.context.repo_playbook import RepoPlaybook
from acp.verification.calibrated_stop import calibrated_stop

# (signature -> the rule a verified fix teaches)
LESSONS = {
    "bugfix:cross_file_api": "use repo_map; the needed constant lives in an unreferenced policy_*.py",
    "bugfix:broad_repo_map": "grep the whole repo; the wiring spans multiple modules",
    "security_fix:none": "add a regression test; do not weaken assertions",
}


def _playbook_eval(sessions: int) -> dict:
    pb = RepoPlaybook(repo_family="repoX")
    coverage_curve = []
    for s in range(sessions):
        for sig, rule in LESSONS.items():
            pb.record_success(failure_signature=sig, rule=rule, now=float(s))
        coverage_curve.append(sum(1 for sig in LESSONS if pb.covers(sig)))
    # precision: for each signature, does the rendered playbook surface the CORRECT lesson first?
    correct_first = 0
    for sig, rule in LESSONS.items():
        rendered = pb.render(failure_signature=sig)
        first = rendered.splitlines()[1] if len(rendered.splitlines()) > 1 else ""
        correct_first += int(sig in first and rule[:20] in first)
    return {"sessions": sessions, "coverage_curve": coverage_curve,
            "all_signatures_covered": coverage_curve[-1] == len(LESSONS),
            "signature_relevant_first_precision": round(correct_first / len(LESSONS), 3),
            "rendered_example": pb.render(failure_signature="bugfix:cross_file_api")}


def _calibrated_stop_eval() -> dict:
    # candidates with a TRUE correctness label + a judge confidence + a sufficiency score
    cases = [
        {"correct": True, "judge": 0.9, "suff": 0.9, "risk": "low"},
        {"correct": False, "judge": 0.55, "suff": 0.8, "risk": "low"},   # weak -> must NOT commit
        {"correct": False, "judge": 0.95, "suff": 0.3, "risk": "low"},   # insufficient -> human
        {"correct": True, "judge": 0.88, "suff": 0.95, "risk": "high"},  # high-risk needs 0.85
        {"correct": False, "judge": 0.8, "suff": 0.9, "risk": "high"},   # below high bar -> human
    ]
    committed = wrong_commits = 0
    rows = []
    for c in cases:
        d = calibrated_stop(judge_confidence=c["judge"], sufficiency_score=c["suff"], risk_level=c["risk"])
        if d.action == "commit":
            committed += 1
            if not c["correct"]:
                wrong_commits += 1
        rows.append({**c, "decision": d.action, "confidence": d.confidence})
    return {"n": len(cases), "committed": committed, "wrong_commits": wrong_commits,
            "no_confident_but_wrong_commit": wrong_commits == 0, "decisions": rows}


def run(sessions: int) -> dict:
    pb = _playbook_eval(sessions)
    cs = _calibrated_stop_eval()
    return {
        "experiment": "verification_frontier",
        "question": "does the repo playbook accumulate the right context, and does calibrated abstention avoid confident-but-wrong commits?",
        "playbook": pb,
        "calibrated_stop": cs,
        "evidence_tier": "deterministic policy benchmark (ACE playbook accumulation + Sufficient-Context calibration)",
        "honest_note": "live solve-rate uplift from injecting the evolved playbook needs model calls; measured here is the policy (accumulation/precision + calibrated precision), not a live model improvement.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=5)
    ap.add_argument("--out", default="reports/verification_frontier.json")
    args = ap.parse_args()
    rep = run(args.sessions)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + "\n")
    print("=== VERIFICATION FRONTIER (Increment 4) ===")
    p = rep["playbook"]
    print(f"playbook: covers all signatures={p['all_signatures_covered']}, relevant-first precision={p['signature_relevant_first_precision']}")
    c = rep["calibrated_stop"]
    print(f"calibrated stop: committed {c['committed']}/{c['n']}, wrong commits={c['wrong_commits']} (no confident-but-wrong: {c['no_confident_but_wrong_commit']})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
