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


@dataclass
class CalibrationReport:
    n: int = 0
    accuracy: float = 0.0
    brier: float = 0.0
    correlation: float = 0.0
    by_source: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "accuracy": round(self.accuracy, 4),
            "brier": round(self.brier, 4),
            "correlation": round(self.correlation, 4),
            "by_source": self.by_source,
        }


def calibrate(samples: list[CalibrationSample], threshold: float = 0.5) -> CalibrationReport:
    if not samples:
        return CalibrationReport()
    preds = [s.predicted for s in samples]
    truths = [1.0 if s.truth else 0.0 for s in samples]
    correct = sum(1 for s in samples if (s.predicted >= threshold) == s.truth)
    brier = sum((p - t) ** 2 for p, t in zip(preds, truths, strict=False)) / len(samples)
    by_source: dict[str, dict] = {}
    sources = {s.source for s in samples}
    for src in sources:
        sub = [s for s in samples if s.source == src]
        c = sum(1 for s in sub if (s.predicted >= threshold) == s.truth)
        by_source[src] = {"n": len(sub), "accuracy": round(c / len(sub), 4)}
    return CalibrationReport(
        n=len(samples),
        accuracy=correct / len(samples),
        brier=brier,
        correlation=_correlation(preds, truths),
        by_source=by_source,
    )
