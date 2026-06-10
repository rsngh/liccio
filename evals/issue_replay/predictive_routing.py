# ruff: noqa: E501
"""Predictive routing eval — does the difficulty probe beat blind cheapest-first? (Prong C)

Labels each bundle with whether the CHEAP rung actually failed it (from the inproc repair reports),
computes intake-only features, and evaluates the probe LEAVE-ONE-OUT (train on n-1, predict the held
out) — never trained-on-test, because n is only a few dozen. Reports: LOO accuracy of the "skip the
cheap rung" decision, doomed cheap attempts correctly skipped, easy bundles correctly kept, and the
net cheap-attempt cost saved vs blind cheapest-first (which pays for the cheap rung every time).

    uv run python -m evals.issue_replay.predictive_routing --out reports/issue_replay_predictive_routing.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.issue_replay.replay_task import IssueReplayTask

from acp.routing.difficulty_probe import FEATURE_NAMES, DifficultyProbe, features

# (bundle full-file, inproc-repair report) pairs — index-aligned per corpus
SOURCES = [
    ("reports/real_issue_replay_full.json", "reports/issue_replay_repair_real_gemini.json", 17),
    ("reports/real_issue_replay_full_hard.json", "reports/issue_replay_repair_hard.json", 10),
]
CHEAP_COST = 0.02  # effective-cost unit for one cheap-rung attempt (matches the economics prior)


def _load() -> tuple[list[list[float]], list[int]]:
    xs: list[list[float]] = []
    ys: list[int] = []
    for bundle_file, label_file, lim in SOURCES:
        if not (Path(bundle_file).exists() and Path(label_file).exists()):
            continue
        bundles = [IssueReplayTask(**d) for d in json.loads(Path(bundle_file).read_text())][:lim]
        labels = json.loads(Path(label_file).read_text())["per_bundle"][:lim]
        for b, lab in zip(bundles, labels, strict=True):
            xs.append(features(issue_title=b.issue_title, issue_body=b.issue_body,
                               module_src=b.buggy, test_src=b.hidden_test,
                               n_extra_files=len(b.extra_files)))
            ys.append(0 if lab["hidden_pass"] else 1)  # 1 = cheap rung FAILED (doomed)
    return xs, ys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--out", default="reports/issue_replay_predictive_routing.json")
    args = ap.parse_args()
    xs, ys = _load()
    n = len(xs)
    n_doomed = sum(ys)
    # leave-one-out p_fail for each bundle (model never sees its own label)
    loo_p = []
    for i in range(n):
        tr_x = [xs[j] for j in range(n) if j != i]
        tr_y = [ys[j] for j in range(n) if j != i]
        loo_p.append(DifficultyProbe().fit(tr_x, tr_y).predict(xs[i]))

    def policy(threshold: float) -> dict:
        sd = se = kd = ke = 0
        for p, y in zip(loo_p, ys, strict=True):
            skip = p >= threshold
            if skip and y:
                sd += 1
            elif skip and not y:
                se += 1      # easy win LOST (skipped a rung that would have solved it cheaply)
            elif not skip and y:
                kd += 1      # blind-equivalent: paid for a doomed cheap attempt
            else:
                ke += 1
        return {"skipped_doomed": sd, "easy_wins_lost": se, "kept_doomed": kd, "kept_easy": ke}

    # honest question: is there ANY threshold that skips doomed attempts with ZERO easy wins lost?
    sweep = {round(t, 2): policy(t) for t in [x / 100 for x in range(50, 100, 5)]}
    zero_regret = {t: m for t, m in sweep.items() if m["easy_wins_lost"] == 0 and m["skipped_doomed"] > 0}
    best_t = max(zero_regret, key=lambda t: zero_regret[t]["skipped_doomed"], default=None)
    m = policy(args.threshold)
    skipped_doomed, skipped_easy, kept_doomed, kept_easy = (
        m["skipped_doomed"], m["easy_wins_lost"], m["kept_doomed"], m["kept_easy"])
    correct = sum(int((p >= args.threshold) == bool(y)) for p, y in zip(loo_p, ys, strict=True))
    preds = [{"doomed": y, "p_fail": round(p, 3), "skipped_cheap": int(p >= args.threshold)}
             for p, y in zip(loo_p, ys, strict=True)]
    # full-data fit for the shipped weights + feature attribution
    probe_full = DifficultyProbe().fit(xs, ys)
    # cost: blind pays CHEAP_COST * n; predictive pays only for kept attempts (n - skipped)
    blind_cost = round(CHEAP_COST * n, 4)
    pred_cost = round(CHEAP_COST * (kept_doomed + kept_easy), 4)
    rep = {
        "experiment": "issue_replay_predictive_routing",
        "question": "can an intake-only probe skip doomed cheap attempts without dropping easy wins? (leave-one-out)",
        "n_bundles": n, "n_doomed_cheap_rung": n_doomed, "threshold": args.threshold,
        "loo_accuracy": round(correct / n, 3),
        "skipped_doomed": skipped_doomed, "skipped_easy_MISTAKE": skipped_easy,
        "kept_doomed_blindlike": kept_doomed, "kept_easy_correct": kept_easy,
        "blind_cheap_cost": blind_cost, "predictive_cheap_cost": pred_cost,
        "cheap_cost_saved_pct": round(100 * (blind_cost - pred_cost) / blind_cost, 1) if blind_cost else 0,
        "best_zero_regret_threshold": best_t,
        "best_zero_regret_skips": zero_regret.get(best_t, {}).get("skipped_doomed", 0) if best_t else 0,
        "threshold_sweep": sweep,
        "verdict": ("useful: a zero-easy-win-loss threshold skips real doomed attempts"
                    if best_t else
                    f"INSUFFICIENT SIGNAL at n={n}: no threshold skips doomed attempts without losing easy wins; "
                    "intake-only features can't isolate the cheap-winnable minority — needs more labels or a cheap dry-run signal"),
        "shipped_weights": dict(zip(("bias", *FEATURE_NAMES), [round(w, 3) for w in probe_full.weights], strict=True)),
        "evidence_tier": "leave-one-out logistic over intake-only features; labels = did the cheap inproc rung fail; no gold/oracle access",
        "predictions": preds,
    }
    Path(args.out).write_text(json.dumps(rep, indent=2) + "\n")
    print(f"\n=== PREDICTIVE ROUTING (LOO, n={n}, {n_doomed} doomed) ===")
    print(f"LOO accuracy {rep['loo_accuracy']}  | skipped_doomed {skipped_doomed}  "
          f"skipped_easy(mistake) {skipped_easy}  kept_doomed {kept_doomed}  kept_easy {kept_easy}")
    print(f"cheap-attempt cost: blind {blind_cost} -> predictive {pred_cost} "
          f"(saved {rep['cheap_cost_saved_pct']}%)")
    print(f"best zero-regret threshold: {best_t} (skips {rep['best_zero_regret_skips']} doomed, 0 easy lost)")
    print("VERDICT:", rep["verdict"])
    print("weights:", rep["shipped_weights"])
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
