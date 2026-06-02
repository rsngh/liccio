"""Drift lifecycle integration (Alpha 9/10, WS5).

Wires the drift detector into a lifecycle: given recent realized outcomes for a
promoted learned model, run drift detection; if a demotion is warranted, demote
the model back to advisory, emit a `ModelDemotionEvent`, and — when the cause is a
high-risk false negative — open a `HumanReviewItem` so a human inspects the case.

This keeps the safety loop closed without new DB tables: demotion events are
returned as domain objects (persistable as `AuditEvent`s by the caller) and the
review item reuses the existing `HumanReviewItem` schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.time import utcnow
from acp.learning.drift import AutoDemoter, DriftReport, WindowedOutcome, detect_drift
from acp.schemas.human_review import HumanReviewItem


@dataclass
class ModelDemotionEvent:
    model_name: str
    reason: str
    accuracy_drop: float
    psi: float
    high_risk_false_negative_rate: float
    created_at: str = field(default_factory=lambda: utcnow().isoformat())

    def as_dict(self) -> dict:
        return {
            "model_name": self.model_name, "reason": self.reason,
            "accuracy_drop": round(self.accuracy_drop, 4), "psi": round(self.psi, 4),
            "high_risk_false_negative_rate": round(self.high_risk_false_negative_rate, 4),
            "created_at": self.created_at,
        }


@dataclass
class DriftLifecycleResult:
    drift: DriftReport
    demoted: bool
    demotion_event: ModelDemotionEvent | None
    review_item: HumanReviewItem | None

    def as_dict(self) -> dict:
        return {
            "drift": self.drift.as_dict(),
            "demoted": self.demoted,
            "demotion_event": self.demotion_event.as_dict() if self.demotion_event else None,
            "review_item_id": self.review_item.id if self.review_item else None,
        }


def run_drift_lifecycle(
    ensemble,
    *,
    model_name: str,
    baseline: list[WindowedOutcome],
    recent: list[WindowedOutcome],
    task_id: str = "drift-monitor",
) -> DriftLifecycleResult:
    """Detect drift on a promoted model and, if warranted, demote + open a review."""
    report = detect_drift(baseline, recent)
    demoted = AutoDemoter().apply(ensemble, report)
    event: ModelDemotionEvent | None = None
    review: HumanReviewItem | None = None
    if demoted:
        event = ModelDemotionEvent(
            model_name=model_name,
            reason="; ".join(report.reasons) or "drift",
            accuracy_drop=report.accuracy_drop, psi=report.psi,
            high_risk_false_negative_rate=report.high_risk_false_negative_rate_recent,
        )
        # A high-risk false negative is the costliest failure -> human review.
        if report.high_risk_false_negative_rate_recent > 0:
            review = HumanReviewItem(
                task_id=task_id,
                reason=f"learned model '{model_name}' demoted: high-risk false "
                       f"negative rate {report.high_risk_false_negative_rate_recent:.2f}",
                priority=1.0,
                metadata={"source": "drift_lifecycle", "model_name": model_name},
            )
    return DriftLifecycleResult(drift=report, demoted=demoted,
                                demotion_event=event, review_item=review)
