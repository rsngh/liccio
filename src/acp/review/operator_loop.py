"""Operator learning loop (GOALS Alpha 44 P9).

Close the human-in-the-loop product loop: an active learner selects the highest-value review
items (uncertainty × risk × frequency), label quality is tracked (reviewer agreement, override
rate), and human labels update FUTURE routing — but only when reviewers agree and governance
gates pass (high-risk labels stay advisory). Deterministic and dependency-free.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

_RISK_W = {"low": 1.0, "medium": 2.0, "high": 4.0, "critical": 6.0}


def _get(c: Any, k: str, d=None):
    return c.get(k, d) if isinstance(c, dict) else getattr(c, k, d)


@dataclass
class ReviewItem:
    task_id: str
    bucket: str
    uncertainty: float          # 0..1; e.g. verifier/calibration uncertainty
    risk_level: str = "low"
    bucket_frequency: int = 1   # how often this bucket recurs
    cost_impact: float = 0.0

    @property
    def priority(self) -> float:
        # value of a label = how unsure we are x how risky x how often it recurs
        return round(self.uncertainty * _RISK_W.get(self.risk_level, 1.0)
                     * (1 + self.bucket_frequency) ** 0.5 + self.cost_impact, 6)

    def why(self) -> str:
        return (f"uncertainty={self.uncertainty:.2f}, risk={self.risk_level}, "
                f"recurs={self.bucket_frequency}x -> priority {self.priority:.3f}")


def active_learning_queue(items: list[ReviewItem], *, k: int = 10) -> list[ReviewItem]:
    """Select the top-k highest-value items for human review (most informative first)."""
    return sorted(items, key=lambda it: -it.priority)[:k]


@dataclass
class LabelQuality:
    n_labels: int
    reviewer_agreement: float
    override_rate: float
    false_auto_approve_near_miss: int

    def to_dict(self) -> dict:
        return {"n_labels": self.n_labels, "reviewer_agreement": self.reviewer_agreement,
                "override_rate": self.override_rate,
                "false_auto_approve_near_miss": self.false_auto_approve_near_miss}


def label_quality(labels: list[Any]) -> LabelQuality:
    """labels: {bucket, reviewers:[verdicts], system_verdict}."""
    n = len(labels)
    agree = 0
    overrides = 0
    near_miss = 0
    for lb in labels:
        revs = _get(lb, "reviewers", []) or []
        if revs and all(r == revs[0] for r in revs):
            agree += 1
        sysv = _get(lb, "system_verdict")
        human = revs[0] if revs else None
        if human is not None and sysv is not None and human != sysv:
            overrides += 1
            if sysv == "approve" and human == "reject":
                near_miss += 1
    return LabelQuality(n, round(agree / n, 4) if n else 0.0,
                        round(overrides / n, 4) if n else 0.0, near_miss)


@dataclass
class PolicyUpdate:
    bucket: str
    old_action: str
    new_action: str
    applied: bool
    reason: str


def policy_update_from_labels(labels: list[Any], current_routing: dict[str, str]) -> dict:
    """Replay: apply human-preferred actions per bucket ONLY when reviewers agree; a high-risk
    bucket update stays ADVISORY until governance gates pass; disagreement BLOCKS learning."""
    by_bucket: dict[str, list[Any]] = defaultdict(list)
    for lb in labels:
        by_bucket[str(_get(lb, "bucket", "default"))].append(lb)
    updates: list[PolicyUpdate] = []
    new_routing = dict(current_routing)
    for bucket, lbs in by_bucket.items():
        prefs = [_get(lb, "preferred_action") for lb in lbs if _get(lb, "preferred_action")]
        reviewers_agree = all(
            (revs := _get(lb, "reviewers", []) or []) and all(r == revs[0] for r in revs)
            for lb in lbs)
        if not prefs:
            continue
        pref = max(set(prefs), key=prefs.count)
        old = current_routing.get(bucket, "cheap_single")
        high_risk = any(_get(lb, "risk_level") in ("high", "critical") for lb in lbs)
        if not reviewers_agree:
            updates.append(PolicyUpdate(bucket, old, pref, False, "reviewer disagreement blocks"))
        elif high_risk:
            updates.append(PolicyUpdate(bucket, old, pref, False,
                                        "high-risk: advisory until governance gates pass"))
        elif pref != old:
            new_routing[bucket] = pref
            updates.append(PolicyUpdate(bucket, old, pref, True, "label changed future routing"))
        else:
            updates.append(PolicyUpdate(bucket, old, pref, False, "no change"))
    return {"new_routing": new_routing,
            "updates": [u.__dict__ for u in updates],
            "n_applied": sum(1 for u in updates if u.applied)}
