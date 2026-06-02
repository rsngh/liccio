"""Drift detection + auto-demote for promoted learned models (Alpha 9).

Alpha 8 promotes a learned model from advisory to authoritative once it makes
**zero high-risk false negatives** on a holdout set. But the world drifts: task
distributions shift, dependencies change, and a model that was accurate at
promotion time can quietly decay. This module closes the safety loop.

We watch a *promoted* model's predictions against realized outcomes over a recent
window and compare it to a baseline window (e.g. the holdout it was promoted on),
measuring:

  * **accuracy drop** — recent accuracy vs baseline accuracy,
  * **PSI** (population stability index) of the predicted-probability
    distribution, which catches input/output drift even when accuracy lags, and
  * **recent high-risk false-negative rate** — the costliest mistake, which alone
    justifies demotion regardless of headline accuracy.

When drift trips, :class:`AutoDemoter` flips ``learned_promoted`` back to ``False``
so the ensemble reverts to advisory (rules retain safety authority) until the
model is re-promoted by a fresh evaluation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class WindowedOutcome:
    """One observed prediction/outcome pair within a drift window."""

    prediction: float          # P(viable) in [0, 1]
    realized: bool             # True == task was actually viable
    risk_level: str            # e.g. "low" / "medium" / "high" / "critical"
    ordinal: int               # monotone timestamp-ish sequence position


@dataclass
class DriftReport:
    baseline_accuracy: float
    recent_accuracy: float
    accuracy_drop: float
    psi: float
    high_risk_false_negative_rate_recent: float
    drifted: bool
    demote_recommended: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "baseline_accuracy": round(self.baseline_accuracy, 4),
            "recent_accuracy": round(self.recent_accuracy, 4),
            "accuracy_drop": round(self.accuracy_drop, 4),
            "psi": round(self.psi, 4),
            "high_risk_false_negative_rate_recent": round(
                self.high_risk_false_negative_rate_recent, 4),
            "drifted": self.drifted,
            "demote_recommended": self.demote_recommended,
            "reasons": list(self.reasons),
        }


_HIGH_RISK = {"high", "critical"}


def _accuracy(window: list[WindowedOutcome], threshold: float) -> float:
    if not window:
        return 0.0
    correct = sum(1 for o in window if (o.prediction >= threshold) == o.realized)
    return correct / len(window)


def _high_risk_fn_rate(window: list[WindowedOutcome], threshold: float) -> float:
    """Rate of high-risk false negatives: predicted viable but truly not viable."""
    hr = [o for o in window if o.risk_level.lower() in _HIGH_RISK]
    if not hr:
        return 0.0
    fn = sum(1 for o in hr if o.prediction >= threshold and not o.realized)
    return fn / len(hr)


def _psi(baseline: list[float], recent: list[float], bins: int = 10) -> float:
    """Population stability index of two probability distributions.

    Standard PSI over equal-width bins on ``[0, 1]``. Empty bins are guarded with
    a small epsilon so a missing population segment yields a large-but-finite
    contribution rather than a division-by-zero or ``inf``.
    """
    if not baseline or not recent:
        return 0.0
    eps = 1e-6
    nb, nr = len(baseline), len(recent)
    psi = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bc = sum(1 for p in baseline if (lo < p <= hi) or (b == 0 and p <= lo))
        rc = sum(1 for p in recent if (lo < p <= hi) or (b == 0 and p <= lo))
        b_pct = max(bc / nb, eps)
        r_pct = max(rc / nr, eps)
        psi += (r_pct - b_pct) * math.log(r_pct / b_pct)
    return psi


def detect_drift(
    baseline: list[WindowedOutcome],
    recent: list[WindowedOutcome],
    *,
    max_accuracy_drop: float = 0.1,
    max_psi: float = 0.25,
    threshold: float = 0.5,
) -> DriftReport:
    """Compare a recent window to a baseline window for concept/accuracy drift.

    ``drifted`` trips when accuracy degrades by more than ``max_accuracy_drop`` OR
    the predicted-probability PSI exceeds ``max_psi``. ``demote_recommended`` trips
    on any drift OR any recent high-risk false negative — the latter is the
    costliest mistake and alone justifies reverting the model to advisory.
    """
    base_acc = _accuracy(baseline, threshold)
    recent_acc = _accuracy(recent, threshold)
    acc_drop = base_acc - recent_acc
    psi = _psi([o.prediction for o in baseline], [o.prediction for o in recent])
    hr_fn_rate = _high_risk_fn_rate(recent, threshold)

    reasons: list[str] = []
    if acc_drop > max_accuracy_drop:
        reasons.append(
            f"accuracy_drop {acc_drop:.4f} > max {max_accuracy_drop}")
    if psi > max_psi:
        reasons.append(f"psi {psi:.4f} > max {max_psi}")
    drifted = bool(reasons)
    if hr_fn_rate > 0:
        reasons.append(
            f"recent high-risk false-negative rate {hr_fn_rate:.4f} > 0")
    demote_recommended = drifted or hr_fn_rate > 0

    return DriftReport(
        baseline_accuracy=base_acc,
        recent_accuracy=recent_acc,
        accuracy_drop=acc_drop,
        psi=psi,
        high_risk_false_negative_rate_recent=hr_fn_rate,
        drifted=drifted,
        demote_recommended=demote_recommended,
        reasons=reasons,
    )


class _Promotable(Protocol):
    learned_promoted: bool


@dataclass
class AutoDemoter:
    """Reverts a promoted ensemble to advisory when drift recommends demotion."""

    def apply(self, ensemble: _Promotable, drift_report: DriftReport) -> bool:
        """Demote ``ensemble`` if drift recommends it and it is currently promoted.

        Returns ``True`` when a demotion happened, ``False`` otherwise (no drift,
        or already advisory). Duck-typed on the ``learned_promoted`` attribute so
        it works on :class:`EnsembleViabilityAssessor` without importing it.
        """
        if drift_report.demote_recommended and ensemble.learned_promoted:
            ensemble.learned_promoted = False
            return True
        return False
