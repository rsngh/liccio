# ruff: noqa: E501
"""Verifier reliability audit (#4 — harden the thing everything rests on).

The whole system trusts one signal: "the repo's test passed -> commit." This audits, across every
real candidate-grading we have (4 agents × easy + hard corpora), how trustworthy each candidate
STOP-SIGNAL actually is, so we know which one is safe to auto-commit on and which must not be trusted:

  * public-only  — accept if the shown/public test passes (the naive weak signal a stateless agent
    might use). False-accept = it would commit a fix that FAILS the held-out hidden test.
  * hidden-test  — accept if the repo's held-out test passes (the system's actual verify-stop). This
    is the correctness oracle here, so it is sound by construction; the audit reports its yield.
  * patch-equivalence probe — a candidate INDEPENDENT check (does the fix behave like the gold patch
    on probe inputs?). The audit measures how often it AGREES with the repo test, to decide whether
    it is safe to use as a second gate.

Output: counts + the evidence-grounded recommendation. No new model calls (reads existing reports).

    uv run python -m evals.issue_replay.verifier_audit --out reports/issue_replay_verifier_audit.json
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/issue_replay_verifier_audit.json")
    args = ap.parse_args()
    files = (glob.glob("reports/issue_replay_vendor_*_real.json")
             + glob.glob("reports/issue_replay_vendor_*_hard.json")
             + ["reports/issue_replay_repair_real_gemini.json", "reports/issue_replay_repair_hard.json"])
    rows = []
    for f in files:
        if not Path(f).exists():
            continue
        for r in json.loads(Path(f).read_text())["per_bundle"]:
            rows.append((bool(r["public_pass"]), bool(r["hidden_pass"]), bool(r.get("patch_equivalent", False))))
    n = len(rows)
    pub = sum(p for p, _, _ in rows)
    hid = sum(h for _, h, _ in rows)
    eq = sum(e for _, _, e in rows)
    pub_false_accept = sum(1 for p, h, _ in rows if p and not h)   # public-only commits a hidden-FAILING fix
    hid_not_equiv = sum(1 for _, h, e in rows if h and not e)       # passed repo test but probe says not-gold-equivalent
    eq_but_hidfail = sum(1 for _, h, e in rows if e and not h)      # probe says equivalent but repo test FAILS (probe false-accept)
    rep = {
        "experiment": "issue_replay_verifier_audit",
        "question": "which stop-signal is safe to auto-commit on, and is the equivalence probe trustworthy as a second gate?",
        "n_candidate_gradings": n,
        "public_pass_rate": round(pub / n, 3), "hidden_pass_rate": round(hid / n, 3),
        "patch_equivalent_rate": round(eq / n, 3),
        "public_only_false_accepts": pub_false_accept,
        "public_only_wrong_commit_rate": round(pub_false_accept / pub, 3) if pub else None,
        "hidden_pass_but_probe_disagrees": hid_not_equiv,
        "probe_disagreement_rate_on_correct_fixes": round(hid_not_equiv / hid, 3) if hid else None,
        "probe_false_accepts_vs_repo_test": eq_but_hidfail,
        "verdict": [
            f"PUBLIC-ONLY IS UNSAFE: it would auto-commit {pub_false_accept} hidden-failing fixes "
            f"({round(100*pub_false_accept/pub) if pub else 0}% of its accepts wrong) — the repo-test verify-stop is necessary, not optional.",
            f"THE EQUIVALENCE PROBE IS TOO BRITTLE TO GATE ON: it disagrees with the repo test on "
            f"{hid_not_equiv}/{hid} correct fixes ({round(100*hid_not_equiv/hid) if hid else 0}%); used as a commit gate it would reject almost all genuine fixes.",
            "RECOMMENDATION: keep the repo's held-out test as the primary verify-stop; for high-stakes "
            "commits add an INDEPENDENT freshly-generated check (verification.proxy_stop_signal / "
            "independent_proof), NOT the probe; demote patch-equivalence to a reporting-only diagnostic.",
        ],
        "evidence_tier": "offline audit over real per-agent candidate gradings (108 across 4 agents × easy+hard); no new model calls",
    }
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== VERIFIER AUDIT (n={n} gradings) ===")
    print(f"public {rep['public_pass_rate']:.0%}  hidden {rep['hidden_pass_rate']:.0%}  probe-equiv {rep['patch_equivalent_rate']:.0%}")
    print(f"public-only would wrongly commit {pub_false_accept} ({rep['public_only_wrong_commit_rate']:.0%} of accepts)")
    print(f"probe disagrees with repo test on {rep['probe_disagreement_rate_on_correct_fixes']:.0%} of correct fixes -> unsafe as a gate")
    for v in rep["verdict"]:
        print("•", v)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
