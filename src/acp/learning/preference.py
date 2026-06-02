"""Preference / reward learning from human labels (Alpha 9).

Human review gives per-attempt verdicts and scores (see
:class:`acp.schemas.human_review.HumanLabel`). On their own those are noisy
absolute signals. This module derives *pairwise* preferences ("attempt A was
preferred over attempt B for the same task") and fits a simple
Bradley-Terry / logistic preference model that scores attempts. The learned
score is a reward that routing / evaluation can use instead of (or alongside)
the objective scalar.

The logistic fit reuses :func:`acp.routing.supervised.train_predictor`, which
lazy-imports scikit-learn and degrades to a mean predictor. When the model is
unfit (or sklearn is absent) :meth:`PreferenceModel.score` falls back to a
deterministic sum of normalized features so it always produces a usable reward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.core.enums import HumanVerdict
from acp.routing.supervised import TrainResult, predict, train_predictor
from acp.schemas.human_review import HumanLabel

# Verdict ordering for tie-breaking when scores are equal (higher == better).
_VERDICT_RANK: dict[HumanVerdict, int] = {
    HumanVerdict.PASS: 3,
    HumanVerdict.PARTIAL: 2,
    HumanVerdict.UNCERTAIN: 1,
    HumanVerdict.FAIL: 0,
}


@dataclass
class Preference:
    """A single pairwise comparison: ``winner`` was preferred over ``loser``."""

    task_id: str
    winner_features: dict[str, float]
    loser_features: dict[str, float]


def _label_rank(label: HumanLabel) -> tuple[int, float]:
    """Sort key for a label; higher verdict rank then higher score wins."""
    return (_VERDICT_RANK.get(label.verdict, 0), float(label.score))


def pairs_from_labels(
    labels: list[HumanLabel],
    features_by_attempt: dict[str, dict[str, float]],
) -> list[Preference]:
    """Build pairwise preferences from per-attempt human labels.

    For each task, every attempt that ranks strictly higher (better verdict, or
    equal verdict and higher score) than another is emitted as the winner over
    that lower-ranked attempt. Attempts without a known ``attempt_id`` or
    without extracted features are skipped. Ordering is deterministic: labels
    are grouped by ``task_id`` and compared in ascending ``attempt_id`` order.
    """
    by_task: dict[str, list[HumanLabel]] = {}
    for label in labels:
        if label.attempt_id is None:
            continue
        if label.attempt_id not in features_by_attempt:
            continue
        by_task.setdefault(label.task_id, []).append(label)

    prefs: list[Preference] = []
    for task_id in sorted(by_task):
        task_labels = sorted(by_task[task_id], key=lambda lbl: lbl.attempt_id or "")
        for i, a in enumerate(task_labels):
            for b in task_labels[i + 1:]:
                ra, rb = _label_rank(a), _label_rank(b)
                if ra == rb:
                    continue
                if ra > rb:
                    winner, loser = a, b
                else:
                    winner, loser = b, a
                assert winner.attempt_id is not None  # narrowed above
                assert loser.attempt_id is not None
                prefs.append(
                    Preference(
                        task_id=task_id,
                        winner_features=features_by_attempt[winner.attempt_id],
                        loser_features=features_by_attempt[loser.attempt_id],
                    )
                )
    return prefs


def _feature_keys(prefs: list[Preference]) -> list[str]:
    keys: set[str] = set()
    for p in prefs:
        keys.update(p.winner_features)
        keys.update(p.loser_features)
    return sorted(keys)


def _diff(
    a: dict[str, float], b: dict[str, float], keys: list[str]
) -> dict[str, float]:
    return {k: float(a.get(k, 0.0)) - float(b.get(k, 0.0)) for k in keys}


@dataclass
class PreferenceModel:
    """A Bradley-Terry style logistic preference model over attempt features.

    :meth:`fit` trains a logistic model on feature *differences*: each pair
    contributes ``(winner - loser) -> 1`` and the negated ``(loser - winner) ->
    0`` so the decision boundary passes through the origin. :meth:`score`
    returns the linear utility of an attempt (a learned reward); higher means
    more preferred. When unfit or when sklearn is unavailable the model falls
    back to a deterministic sum of min-max normalized features.
    """

    _model: TrainResult | None = None
    _feature_keys: list[str] = field(default_factory=list)
    _feature_min: dict[str, float] = field(default_factory=dict)
    _feature_max: dict[str, float] = field(default_factory=dict)

    @property
    def is_fit(self) -> bool:
        """True once a logistic (sklearn-backed) model has been trained."""
        return self._model is not None and self._model.backend == "sklearn"

    def fit(self, prefs: list[Preference]) -> None:
        """Train the logistic preference model from pairwise comparisons."""
        keys = _feature_keys(prefs)
        self._feature_keys = keys
        self._fit_normalization(prefs, keys)
        if not prefs:
            return
        rows: list[dict[str, Any]] = []
        for p in prefs:
            pos = _diff(p.winner_features, p.loser_features, keys)
            pos["label"] = 1.0
            rows.append(pos)
            neg = _diff(p.loser_features, p.winner_features, keys)
            neg["label"] = 0.0
            rows.append(neg)
        self._model = train_predictor(rows, "label", keys)

    def _fit_normalization(self, prefs: list[Preference], keys: list[str]) -> None:
        self._feature_min = {}
        self._feature_max = {}
        for k in keys:
            vals: list[float] = []
            for p in prefs:
                vals.append(float(p.winner_features.get(k, 0.0)))
                vals.append(float(p.loser_features.get(k, 0.0)))
            if vals:
                self._feature_min[k] = min(vals)
                self._feature_max[k] = max(vals)

    def _fallback_score(self, features: dict[str, float]) -> float:
        """Deterministic reward: sum of min-max normalized feature values."""
        keys = self._feature_keys or sorted(features)
        total = 0.0
        for k in keys:
            v = float(features.get(k, 0.0))
            lo = self._feature_min.get(k, 0.0)
            hi = self._feature_max.get(k, 0.0)
            total += (v - lo) / (hi - lo) if hi > lo else v
        return total

    def score(self, features: dict[str, float]) -> float:
        """Return a learned reward for an attempt (higher == more preferred)."""
        if self._model is None or self._model.backend != "sklearn":
            return self._fallback_score(features)
        vec = {k: float(features.get(k, 0.0)) for k in self._feature_keys}
        return predict(self._model, vec)

    def prefers(self, a: dict[str, float], b: dict[str, float]) -> bool:
        """True if attempt ``a`` is preferred over attempt ``b``."""
        return self.score(a) > self.score(b)


def evaluate_preference_model(
    model: PreferenceModel, held_out_prefs: list[Preference]
) -> dict[str, float]:
    """Pairwise accuracy: fraction of held-out pairs scored in the right order."""
    if not held_out_prefs:
        return {"pairwise_accuracy": 0.0, "n": 0.0}
    correct = sum(
        1
        for p in held_out_prefs
        if model.score(p.winner_features) > model.score(p.loser_features)
    )
    n = len(held_out_prefs)
    return {"pairwise_accuracy": correct / n, "n": float(n)}


def default_preference_dataset() -> (
    tuple[list[HumanLabel], dict[str, dict[str, float]]]
):
    """Synthetic labels + features for tests / artifacts (no DB).

    Models a world where "more thorough, verified" attempts are preferred:
    higher ``verified`` (tests/types passed), more ``thoroughness`` (file reads,
    targeted edits) and lower ``waste`` (churn relative to value) earn better
    verdicts and scores. Each task has two attempts, a stronger and a weaker.
    """
    labels: list[HumanLabel] = []
    features: dict[str, dict[str, float]] = {}

    def add(
        task: str,
        attempt: str,
        verdict: HumanVerdict,
        score: float,
        verified: float,
        thoroughness: float,
        waste: float,
    ) -> None:
        features[attempt] = {
            "verified": verified,
            "thoroughness": thoroughness,
            "waste": -waste,  # negate so "more is better" holds for all features
        }
        labels.append(
            HumanLabel(
                review_item_id=f"ri-{attempt}",
                task_id=task,
                attempt_id=attempt,
                verdict=verdict,
                score=score,
                reviewer="synthetic",
            )
        )

    specs = [
        # task, (good verified, thoroughness, waste), (bad ...)
        ("t1", (1.0, 0.8, 0.1), (0.0, 0.3, 0.7)),
        ("t2", (1.0, 0.9, 0.2), (0.0, 0.4, 0.6)),
        ("t3", (1.0, 0.7, 0.1), (1.0, 0.2, 0.5)),
        ("t4", (1.0, 0.6, 0.0), (0.0, 0.5, 0.9)),
        ("t5", (1.0, 1.0, 0.1), (0.0, 0.6, 0.8)),
        ("t6", (1.0, 0.85, 0.15), (0.0, 0.35, 0.65)),
    ]
    for task, good, bad in specs:
        add(task, f"{task}-good", HumanVerdict.PASS, 0.9, *good)
        add(task, f"{task}-bad", HumanVerdict.FAIL, 0.2, *bad)
    return labels, features
