"""Reviewer reliability + preference-reward governance (Alpha 11, WS7).

Human labels drive the pairwise preference reward (``learning/preference.py``),
but not every reviewer is equally trustworthy. This module estimates per-reviewer
reliability against a ground-truth signal and folds that into a governance
evaluation that decides whether the preference reward may be *promoted* into
routing.

The governance evaluation composes three existing pieces:

* :class:`~acp.learning.preference.PreferenceModel` (fit + evaluate) for the
  pairwise accuracy of the learned reward;
* :class:`ReviewerReliabilityModel` (this module) for reviewer agreement with
  ground truth;
* :class:`~acp.learning.preference_reward.PreferenceRewardGate` for the
  promotion decision.

Until every gate condition passes the preference reward stays *advisory*
(``promoted == False``) so routing optimizes the objective reward alone.
Everything is pure, deterministic, and DB-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.enums import HumanVerdict
from acp.learning.preference import (
    PreferenceModel,
    evaluate_preference_model,
    pairs_from_labels,
)
from acp.learning.preference_reward import PreferenceRewardGate
from acp.schemas.human_review import HumanLabel

# A verdict is treated as a "positive" (attempt was good) at or above PARTIAL.
_POSITIVE_VERDICTS: frozenset[HumanVerdict] = frozenset(
    {HumanVerdict.PASS, HumanVerdict.PARTIAL}
)


def _verdict_is_positive(verdict: HumanVerdict) -> bool:
    """Collapse a verdict to a boolean "attempt was good" signal."""
    return verdict in _POSITIVE_VERDICTS


@dataclass
class ReviewerReliabilityModel:
    """Estimate per-reviewer accuracy/agreement against a ground-truth signal.

    :meth:`fit` compares each label's verdict (collapsed to a boolean "good"
    signal) against a per-attempt ground truth. A reviewer's reliability is the
    fraction of their labels that agree with truth; the overall
    :meth:`agreement` is the micro-averaged agreement across all judged labels.
    Reviewers (or labels) without a known ground truth are ignored.
    """

    _reliability: dict[str, float] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)
    _agreement: float = 0.0
    _n_judged: int = 0

    def fit(
        self,
        labels: list[HumanLabel],
        truth_by_attempt: dict[str, bool],
    ) -> None:
        """Estimate reliability from labels vs ``truth_by_attempt``.

        ``truth_by_attempt`` maps ``attempt_id`` -> whether the attempt was
        actually good. A label agrees when its (collapsed) verdict matches that
        truth. Labels for attempts absent from ``truth_by_attempt`` are skipped.
        """
        agree_by_reviewer: dict[str, int] = {}
        total_by_reviewer: dict[str, int] = {}
        total_agree = 0
        total_judged = 0
        for label in labels:
            attempt = label.attempt_id
            if attempt is None or attempt not in truth_by_attempt:
                continue
            reviewer = label.reviewer
            agrees = _verdict_is_positive(label.verdict) == truth_by_attempt[attempt]
            total_by_reviewer[reviewer] = total_by_reviewer.get(reviewer, 0) + 1
            if agrees:
                agree_by_reviewer[reviewer] = agree_by_reviewer.get(reviewer, 0) + 1
                total_agree += 1
            total_judged += 1
        self._reliability = {
            reviewer: agree_by_reviewer.get(reviewer, 0) / n
            for reviewer, n in total_by_reviewer.items()
        }
        self._counts = total_by_reviewer
        self._n_judged = total_judged
        self._agreement = total_agree / total_judged if total_judged else 0.0

    def agreement(self) -> float:
        """Micro-averaged agreement with ground truth across all judged labels."""
        return self._agreement

    def reliability_by_reviewer(self) -> dict[str, float]:
        """Per-reviewer agreement fraction (a copy; higher == more reliable)."""
        return dict(self._reliability)


def evaluate_preference_reward_governance(
    labels: list[HumanLabel],
    features_by_attempt: dict[str, dict[str, float]],
    *,
    truth_by_attempt: dict[str, bool] | None = None,
    post_merge_correlation: float = 0.0,
    high_risk_degradation: float = 0.0,
    gate: PreferenceRewardGate | None = None,
) -> dict:
    """Govern promotion of the preference reward into routing.

    Fits a :class:`~acp.learning.preference.PreferenceModel` from ``labels`` +
    ``features_by_attempt`` and measures its pairwise accuracy, estimates
    reviewer agreement via :class:`ReviewerReliabilityModel`, then runs the
    existing :class:`~acp.learning.preference_reward.PreferenceRewardGate`. The
    reward is ``promoted`` only when every gate condition passes; otherwise it
    stays advisory. Returns::

        {pairwise_accuracy, reviewer_agreement, post_merge_correlation,
         high_risk_degradation, gate, promoted}

    where ``gate`` is the gate's structured decision (``passed`` + per-condition
    ``conditions`` + ``reasons``). When ``truth_by_attempt`` is omitted the
    reviewer agreement is ``0.0`` (and thus blocks promotion on that condition).
    """
    gate = gate or PreferenceRewardGate()

    prefs = pairs_from_labels(labels, features_by_attempt)
    model = PreferenceModel()
    model.fit(prefs)
    pairwise_accuracy = float(evaluate_preference_model(model, prefs)["pairwise_accuracy"])

    reliability = ReviewerReliabilityModel()
    reliability.fit(labels, truth_by_attempt or {})
    reviewer_agreement = reliability.agreement()

    gate_result = gate.evaluate(
        reviewer_agreement=reviewer_agreement,
        pairwise_accuracy=pairwise_accuracy,
        post_merge_correlation=post_merge_correlation,
        high_risk_degradation=high_risk_degradation,
    )
    return {
        "pairwise_accuracy": pairwise_accuracy,
        "reviewer_agreement": reviewer_agreement,
        "post_merge_correlation": post_merge_correlation,
        "high_risk_degradation": high_risk_degradation,
        "reliability_by_reviewer": reliability.reliability_by_reviewer(),
        "gate": gate_result,
        "promoted": bool(gate_result["passed"]),
    }


def default_governance_dataset() -> tuple[
    list[HumanLabel], dict[str, dict[str, float]], dict[str, bool]
]:
    """Synthetic labels + features + ground truth for tests / artifacts (no DB).

    Each task has a strong attempt (verified, thorough, low waste — truly good)
    and a weak one. A reliable reviewer (``"alice"``) labels every attempt to
    match ground truth; her verdicts make the preference model and the reviewer
    agreement both strong, so the governance gate promotes the reward.
    """
    labels: list[HumanLabel] = []
    features: dict[str, dict[str, float]] = {}
    truth: dict[str, bool] = {}

    def add(
        task: str,
        attempt: str,
        verdict: HumanVerdict,
        score: float,
        verified: float,
        thoroughness: float,
        waste: float,
        is_good: bool,
    ) -> None:
        features[attempt] = {
            "verified": verified,
            "thoroughness": thoroughness,
            "waste": -waste,  # negate so "more is better" holds for all features
        }
        truth[attempt] = is_good
        labels.append(
            HumanLabel(
                review_item_id=f"ri-{attempt}",
                task_id=task,
                attempt_id=attempt,
                verdict=verdict,
                score=score,
                reviewer="alice",
            )
        )

    specs = [
        ("t1", (1.0, 0.8, 0.1), (0.0, 0.3, 0.7)),
        ("t2", (1.0, 0.9, 0.2), (0.0, 0.4, 0.6)),
        ("t3", (1.0, 0.7, 0.1), (0.0, 0.2, 0.5)),
        ("t4", (1.0, 0.6, 0.0), (0.0, 0.5, 0.9)),
        ("t5", (1.0, 1.0, 0.1), (0.0, 0.6, 0.8)),
        ("t6", (1.0, 0.85, 0.15), (0.0, 0.35, 0.65)),
    ]
    for task, good, bad in specs:
        add(task, f"{task}-good", HumanVerdict.PASS, 0.9, *good, True)
        add(task, f"{task}-bad", HumanVerdict.FAIL, 0.2, *bad, False)
    return labels, features, truth
