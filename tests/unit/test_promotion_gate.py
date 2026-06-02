"""OPE promotion gate (Alpha 7, WS5)."""

from __future__ import annotations

from acp.routing.ope import OPESample, evaluate_policy
from acp.routing.promotion import (
    PromotionThresholds,
    evaluate_promotion,
)

CANDS = ["good", "bad"]


def _good_log(n: int = 200) -> list[OPESample]:
    out = []
    for i in range(n):
        a = "good" if i % 2 == 0 else "bad"
        out.append(OPESample("ctx", a, 0.5, 1.0 if a == "good" else 0.0, CANDS))
    return out


def _prefer(best: str):
    def pi(ctx, action, cands):
        return 0.9 if action == best else 0.1
    return pi


def test_good_policy_passes_and_gets_canary_plan() -> None:
    rep = evaluate_policy(_good_log(), _prefer("good"), seed=1)
    dec = evaluate_promotion(rep, baseline_value=0.5,
                             thresholds=PromotionThresholds(min_ess=10, min_overlap=0.8))
    assert dec.promote is True
    assert dec.canary_plan is not None and dec.canary_plan.stages[-1] == 1.0
    assert all(c.passed for c in dec.conditions if c.required)


def test_zero_overlap_policy_blocked() -> None:
    # Target only takes an action never logged -> overlap 0.
    log = [OPESample("ctx", "good", 0.5, 1.0, ["good", "bad", "unseen"]) for _ in range(50)]

    def only_unseen(ctx, action, cands):
        return 1.0 if action == "unseen" else 0.0

    rep = evaluate_policy(log, only_unseen, seed=1)
    dec = evaluate_promotion(rep, baseline_value=0.5)
    assert dec.promote is False
    assert any("overlap" in r for r in dec.reasons)


def test_high_variance_policy_blocked_by_weight_and_ess() -> None:
    # One ultra-rare logged action creates a huge importance weight.
    log = [OPESample("ctx", "good", 0.001, 1.0, CANDS)]
    log += _good_log(30)
    rep = evaluate_policy(log, _prefer("good"), weight_clip=10_000, seed=1)
    dec = evaluate_promotion(
        rep, baseline_value=0.5,
        thresholds=PromotionThresholds(min_ess=25, max_weight=50, min_overlap=0.8))
    assert dec.promote is False
    assert any("max_weight" in r or "effective_sample_size" in r for r in dec.reasons)


def test_cost_regressing_policy_blocked() -> None:
    rep = evaluate_policy(_good_log(), _prefer("good"), seed=1)
    dec = evaluate_promotion(
        rep, baseline_value=0.5,
        thresholds=PromotionThresholds(min_ess=10, max_cost_ratio=1.0),
        target_cost=2.0, baseline_cost=1.0)
    assert dec.promote is False
    assert any("cost_cap" in r for r in dec.reasons)


def test_high_risk_regression_blocked() -> None:
    rep = evaluate_policy(_good_log(), _prefer("good"), seed=1)
    dec = evaluate_promotion(
        rep, baseline_value=0.5, thresholds=PromotionThresholds(min_ess=10),
        high_risk_value_delta=-0.2)
    assert dec.promote is False
    assert any("high_risk" in r for r in dec.reasons)


def test_human_review_regression_blocked() -> None:
    rep = evaluate_policy(_good_log(), _prefer("good"), seed=1)
    dec = evaluate_promotion(
        rep, baseline_value=0.5, thresholds=PromotionThresholds(min_ess=10),
        target_human_review_rate=0.5, baseline_human_review_rate=0.2)
    assert dec.promote is False
    assert any("human_review" in r for r in dec.reasons)
