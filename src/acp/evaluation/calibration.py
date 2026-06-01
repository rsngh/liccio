"""Evaluator calibration (round-3 R3-6).

Calibrates automated evaluators (objective spec-compliance, weak-label success
probability, judge scores) against ground truth — human labels and post-merge
outcomes. Reports accuracy, Brier score, and correlation so we know how much to
trust automated signals (round-3 gap §6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class CalibrationSample:
    predicted: float  # automated success probability in [0,1]
    truth: bool       # ground-truth success
    source: str = "objective"  # which automated signal
    truth_source: str = "human"  # human | post_merge


def _correlation(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (vx * vy) if vx and vy else 0.0


def _brier(samples: list[CalibrationSample]) -> float:
    if not samples:
        return 0.0
    return sum((s.predicted - (1.0 if s.truth else 0.0)) ** 2 for s in samples) / len(samples)


def _accuracy(samples: list[CalibrationSample], threshold: float) -> float:
    if not samples:
        return 0.0
    return sum(1 for s in samples if (s.predicted >= threshold) == s.truth) / len(samples)


def recommend_human_review_threshold(samples: list[CalibrationSample]) -> dict:
    """Recommend a confidence threshold below which an attempt should be sent to
    human review. We pick the prediction level that maximizes overall accuracy,
    and report the residual false-confident-pass rate above it (predicted pass
    but truth fail) — the risk a reviewer would catch.
    """
    if not samples:
        return {"threshold": 0.5, "auto_accuracy_above": 0.0, "false_confident_pass": 0.0}
    grid = [i / 20 for i in range(1, 20)]
    best_t, best_acc = 0.5, -1.0
    for t in grid:
        acc = _accuracy(samples, t)
        if acc > best_acc:
            best_acc, best_t = acc, t
    above = [s for s in samples if s.predicted >= best_t]
    fcp = sum(1 for s in above if not s.truth) / len(above) if above else 0.0
    return {"threshold": round(best_t, 4),
            "auto_accuracy_above": round(best_acc, 4),
            "false_confident_pass": round(fcp, 4),
            "auto_approvable_fraction": round(len(above) / len(samples), 4)}


@dataclass
class CalibrationReport:
    n: int = 0
    accuracy: float = 0.0
    brier: float = 0.0
    correlation: float = 0.0
    by_source: dict = field(default_factory=dict)
    threshold_recommendation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "accuracy": round(self.accuracy, 4),
            "brier": round(self.brier, 4),
            "correlation": round(self.correlation, 4),
            "by_source": self.by_source,
            "threshold_recommendation": self.threshold_recommendation,
        }


def calibrate(samples: list[CalibrationSample], threshold: float = 0.5) -> CalibrationReport:
    if not samples:
        return CalibrationReport()
    preds = [s.predicted for s in samples]
    truths = [1.0 if s.truth else 0.0 for s in samples]
    correct = sum(1 for s in samples if (s.predicted >= threshold) == s.truth)
    by_source: dict[str, dict] = {}
    for src in {s.source for s in samples}:
        sub = [s for s in samples if s.source == src]
        c = sum(1 for s in sub if (s.predicted >= threshold) == s.truth)
        by_source[src] = {
            "n": len(sub),
            "accuracy": round(c / len(sub), 4),
            "brier": round(_brier(sub), 4),
            "correlation": round(_correlation([s.predicted for s in sub],
                                              [1.0 if s.truth else 0.0 for s in sub]), 4),
        }
    return CalibrationReport(
        n=len(samples),
        accuracy=correct / len(samples),
        brier=_brier(samples),
        correlation=_correlation(preds, truths),
        by_source=by_source,
        threshold_recommendation=recommend_human_review_threshold(samples),
    )
