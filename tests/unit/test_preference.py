"""Tests for preference / reward learning from human labels (Alpha 9)."""

from __future__ import annotations

from acp.core.enums import HumanVerdict
from acp.learning.preference import (
    Preference,
    PreferenceModel,
    default_preference_dataset,
    evaluate_preference_model,
    pairs_from_labels,
)
from acp.schemas.human_review import HumanLabel


def _label(task: str, attempt: str, verdict: HumanVerdict, score: float) -> HumanLabel:
    return HumanLabel(
        review_item_id=f"ri-{attempt}",
        task_id=task,
        attempt_id=attempt,
        verdict=verdict,
        score=score,
    )


def test_pairs_from_labels_pass_over_fail_and_higher_score() -> None:
    labels = [
        _label("t1", "a", HumanVerdict.PASS, 0.9),
        _label("t1", "b", HumanVerdict.FAIL, 0.1),
        _label("t2", "c", HumanVerdict.PASS, 0.9),
        _label("t2", "d", HumanVerdict.PASS, 0.4),  # same verdict, lower score
    ]
    feats = {k: {"x": 1.0} for k in ("a", "b", "c", "d")}
    prefs = pairs_from_labels(labels, feats)

    # One pair per task.
    assert len(prefs) == 2
    pairs = {(p.task_id, _name(p, feats)) for p in prefs}
    # PASS beats FAIL; higher score beats lower score for equal verdicts.
    winners = {p.task_id: p for p in prefs}
    assert winners["t1"].winner_features is feats["a"]
    assert winners["t1"].loser_features is feats["b"]
    assert winners["t2"].winner_features is feats["c"]
    assert winners["t2"].loser_features is feats["d"]
    assert pairs  # touch helper


def _name(p: Preference, feats: dict) -> str:
    return next(k for k, v in feats.items() if v is p.winner_features)


def test_pairs_skip_unknown_attempts_and_missing_features() -> None:
    labels = [
        _label("t1", "a", HumanVerdict.PASS, 0.9),
        _label("t1", "b", HumanVerdict.FAIL, 0.1),
        HumanLabel(review_item_id="r", task_id="t1", verdict=HumanVerdict.PASS),
    ]
    feats = {"a": {"x": 1.0}}  # b missing
    assert pairs_from_labels(labels, feats) == []


def test_pairs_deterministic() -> None:
    labels, feats = default_preference_dataset()
    p1 = pairs_from_labels(labels, feats)
    p2 = pairs_from_labels(labels, feats)
    assert [(p.task_id, p.winner_features, p.loser_features) for p in p1] == [
        (p.task_id, p.winner_features, p.loser_features) for p in p2
    ]


def test_fit_then_prefers_known_better() -> None:
    labels, feats = default_preference_dataset()
    prefs = pairs_from_labels(labels, feats)
    model = PreferenceModel()
    model.fit(prefs)
    good = feats["t1-good"]
    bad = feats["t1-bad"]
    assert model.prefers(good, bad)
    assert model.score(good) > model.score(bad)


def test_held_out_pairwise_accuracy() -> None:
    labels, feats = default_preference_dataset()
    prefs = pairs_from_labels(labels, feats)
    split = len(prefs) // 2
    train, held = prefs[:split], prefs[split:]
    model = PreferenceModel()
    model.fit(train)
    metrics = evaluate_preference_model(model, held)
    assert metrics["n"] == float(len(held))
    assert metrics["pairwise_accuracy"] > 0.6


def test_degrades_gracefully_before_fit() -> None:
    model = PreferenceModel()
    # No fit, no sklearn needed: fallback score must still work and rank.
    good = {"verified": 1.0, "thoroughness": 0.9, "waste": -0.1}
    bad = {"verified": 0.0, "thoroughness": 0.3, "waste": -0.7}
    assert isinstance(model.score(good), float)
    assert model.prefers(good, bad)


def test_evaluate_empty() -> None:
    model = PreferenceModel()
    assert evaluate_preference_model(model, []) == {"pairwise_accuracy": 0.0, "n": 0.0}
