"""Tests for the evaluator trust model (Alpha 8, WS4)."""

from __future__ import annotations

from acp.evaluation.evaluator_trust import (
    RISK_LEVELS,
    EvaluatorDisagreementModel,
    EvaluatorTrustModel,
    HumanReviewThresholdPolicy,
    default_trust_dataset,
    evaluate_trust,
)


def _feats(obj=0.9, weak=0.9, spread=0.1, adv=0.1, cx=0.3):
    return {
        "objective_score": obj,
        "weak_label_agreement": weak,
        "judge_spread": spread,
        "adversarial_findings": adv,
        "trace_complexity": cx,
    }


def test_model_trains_and_predicts_in_unit_interval():
    model = EvaluatorTrustModel()
    model.fit(default_trust_dataset())
    for f in (_feats(), _feats(obj=0.85, weak=0.3, spread=0.6, adv=0.7, cx=0.9)):
        p = model.predict_correct(f)
        assert 0.0 <= p <= 1.0


def test_disagreement_higher_when_signals_conflict():
    dm = EvaluatorDisagreementModel()
    agree = dm.score(_feats(obj=0.9, weak=0.9, spread=0.1, adv=0.05))
    conflict = dm.score(_feats(obj=0.9, weak=0.2, spread=0.7, adv=0.8))
    assert conflict > agree
    assert 0.0 <= agree <= 1.0
    assert 0.0 <= conflict <= 1.0


def test_threshold_policy_stricter_for_high_risk():
    model = EvaluatorTrustModel()
    cases = default_trust_dataset()
    model.fit(cases)
    policy = HumanReviewThresholdPolicy(model=model)
    rec = policy.recommend(cases)
    thr = rec["thresholds"]
    assert set(thr) == set(RISK_LEVELS)
    assert thr["high"] > thr["medium"] > thr["low"]


def test_low_risk_threshold_cuts_review_without_more_false_approves():
    cases = default_trust_dataset()
    report = evaluate_trust(cases)

    low_rec = report["projected"]["low"]
    low_fixed = report["fixed_threshold_baseline"]["projected"]["low"]

    # review burden drops at low risk
    assert low_rec["review_rate"] < low_fixed["review_rate"]
    # false-auto-approve rate does NOT increase
    assert (
        low_rec["false_auto_approve_rate"]
        <= low_fixed["false_auto_approve_rate"] + 1e-9
    )
    assert report["burden_reduced_without_more_false_approves"] is True


def test_report_has_metric_keys():
    report = evaluate_trust(default_trust_dataset())
    m = report["metrics"]
    for key in ("accuracy", "precision", "recall", "brier", "ece"):
        assert key in m
        assert isinstance(m[key], float)
