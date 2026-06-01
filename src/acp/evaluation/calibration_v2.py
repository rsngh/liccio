"""Evaluator calibration v2 — per-evaluator metrics (round-5 WS9).

Round-3/4 calibration scored one signal against truth. v2 calibrates *every*
evaluator on the ladder (objective / weak supervision / LLM judge / adversarial
detector / combined) on a labelled scenario set, reporting accuracy,
precision/recall (for the auto-approvable "pass" class), Brier, ECE (expected
calibration error), correlation, a recommended human-review threshold, and the
false-auto-approve risk — the chance of auto-approving a bad change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class EvalCaseV2:
    scenario: str
    truth: bool                       # True == genuinely good (auto-approvable)
    predictions: dict[str, float]     # evaluator name -> P(pass) in [0,1]
    truth_source: str = "human"


def _correlation(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (vx * vy) if vx and vy else 0.0


def _ece(preds: list[float], truths: list[float], bins: int = 5) -> float:
    """Expected calibration error: weighted gap between confidence and accuracy."""
    n = len(preds)
    if n == 0:
        return 0.0
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(preds) if (lo < p <= hi) or (b == 0 and p == 0.0)]
        if not idx:
            continue
        conf = sum(preds[i] for i in idx) / len(idx)
        acc = sum(truths[i] for i in idx) / len(idx)
        total += (len(idx) / n) * abs(conf - acc)
    return total


def _evaluator_metrics(preds: list[float], truths: list[bool], threshold: float) -> dict:
    n = len(preds)
    t = [1.0 if x else 0.0 for x in truths]
    tp = sum(1 for p, y in zip(preds, truths, strict=False) if p >= threshold and y)
    fp = sum(1 for p, y in zip(preds, truths, strict=False) if p >= threshold and not y)
    fn = sum(1 for p, y in zip(preds, truths, strict=False) if p < threshold and y)
    correct = sum(1 for p, y in zip(preds, truths, strict=False) if (p >= threshold) == y)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    brier = sum((p - y) ** 2 for p, y in zip(preds, t, strict=False)) / n if n else 0.0
    # recommend the threshold (over a grid) maximizing accuracy
    best_t, best_acc = threshold, -1.0
    for cand in (i / 20 for i in range(1, 20)):
        acc = sum(1 for p, y in zip(preds, truths, strict=False)
                  if (p >= cand) == y) / n if n else 0.0
        if acc > best_acc:
            best_acc, best_t = acc, cand
    # false-auto-approve risk is measured at the FIXED operating threshold (not
    # each evaluator's self-optimized one) so a naive always-pass signal cannot
    # game its own threshold to look safe.
    above = [(p, y) for p, y in zip(preds, truths, strict=False) if p >= threshold]
    false_auto_approve = (sum(1 for _, y in above if not y) / len(above)) if above else 0.0
    return {
        "n": n,
        "accuracy": round(correct / n, 4) if n else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "brier": round(brier, 4),
        "ece": round(_ece(preds, t), 4),
        "correlation": round(_correlation(preds, t), 4),
        "recommended_threshold": round(best_t, 4),
        "false_auto_approve_risk": round(false_auto_approve, 4),
    }


@dataclass
class CalibrationV2Report:
    n_cases: int = 0
    evaluators: dict = field(default_factory=dict)
    recommended_threshold: float = 0.5

    def to_dict(self) -> dict:
        return {"schema_version": 2, "n_cases": self.n_cases,
                "evaluators": self.evaluators,
                "recommended_threshold": round(self.recommended_threshold, 4)}


def calibrate_v2(cases: list[EvalCaseV2], threshold: float = 0.5) -> CalibrationV2Report:
    if not cases:
        return CalibrationV2Report()
    evaluators = sorted({e for c in cases for e in c.predictions})
    out: dict[str, dict] = {}
    for ev in evaluators:
        rows = [(c.predictions[ev], c.truth) for c in cases if ev in c.predictions]
        preds = [p for p, _ in rows]
        truths = [y for _, y in rows]
        out[ev] = _evaluator_metrics(preds, truths, threshold)
    # the combined evaluator's recommended threshold drives human-review gating
    combined = out.get("combined") or next(iter(out.values()))
    return CalibrationV2Report(n_cases=len(cases), evaluators=out,
                               recommended_threshold=combined["recommended_threshold"])


def default_calibration_dataset() -> list[EvalCaseV2]:
    """A labelled scenario set spanning clean + adversarial change patterns.

    Evaluators differ on purpose: ``objective`` is fooled by hardcoded/test-
    deletion fixes; ``adversarial_detector`` catches them but is trigger-happy;
    ``llm_judge`` is decent; ``naive_optimist`` always says pass (a bad signal);
    ``combined`` averages the trustworthy ones.
    """
    def case(scenario, truth, objective, weak, judge, adversarial):
        naive = 0.9
        combined = round((objective + weak + judge + adversarial) / 4, 3)
        return EvalCaseV2(scenario=scenario, truth=truth, predictions={
            "objective": objective, "weak_supervision": weak, "llm_judge": judge,
            "adversarial_detector": adversarial, "naive_optimist": naive,
            "combined": combined})

    return [
        #     scenario              truth  obj  weak judge adv
        case("clean_fix",           True,  0.95, 0.9, 0.92, 0.85),
        case("good_refactor",       True,  0.9,  0.8, 0.88, 0.8),
        case("well_tested_feature", True,  0.92, 0.85, 0.9, 0.82),
        case("safe_migration",      True,  0.88, 0.8, 0.85, 0.78),
        case("bad_fix",             False, 0.2,  0.3, 0.25, 0.2),
        case("partial_fix",         False, 0.55, 0.4, 0.45, 0.35),
        case("test_deletion",       False, 0.85, 0.3, 0.6, 0.1),   # objective fooled
        case("skip_addition",       False, 0.8,  0.35, 0.55, 0.15),
        case("hardcoded_fix",       False, 0.82, 0.45, 0.5, 0.12),  # objective fooled
        case("security_regression", False, 0.7,  0.5, 0.4, 0.08),
        case("large_unrelated_diff", False, 0.6, 0.5, 0.45, 0.3),
        case("post_merge_revert",   False, 0.75, 0.4, 0.5, 0.2),
    ]
