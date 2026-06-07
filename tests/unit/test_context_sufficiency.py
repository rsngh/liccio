"""Context sufficiency + abstain gate tests (GOALS Alpha 42 P5)."""

from __future__ import annotations

from acp.evaluation.context_sufficiency import (
    Sufficiency,
    SufficiencySignals,
    assess,
    extract_signals,
)
from acp.routing.answer_or_abstain_gate import answer_or_abstain
from acp.routing.spec_needed_gate import spec_needed


def test_missing_acceptance_routes_to_spec_needed() -> None:
    sig = SufficiencySignals(has_acceptance_criteria=False)
    d = assess(sig, risk_level="low")
    assert d.outcome == Sufficiency.NEED_USER_SPEC.value
    assert d.recommended_action == "ask_user_spec"
    assert spec_needed(acceptance_criteria=None, has_tests=False,
                       ambiguous_target=False).spec_needed


def test_missing_api_definition_routes_to_repo_map_retry() -> None:
    sig = SufficiencySignals(referenced_apis=("apply_house_discount",),
                             defined_symbols=frozenset({"checkout_total"}))
    d = assess(sig, risk_level="medium")
    assert d.outcome == Sufficiency.NEED_MORE_CONTEXT.value
    assert d.recommended_action == "retry_with_repo_map"
    assert "apply_house_discount" in d.reasons[0]


def test_conflicting_docs_code_routes_to_advisor_or_human() -> None:
    low = assess(SufficiencySignals(conflicting_docs_code=True), risk_level="low")
    assert low.recommended_action == "ask_advisor"
    high = assess(SufficiencySignals(conflicting_docs_code=True), risk_level="high")
    assert high.recommended_action == "human_review"
    assert high.outcome == Sufficiency.NEED_HUMAN_REVIEW.value


def test_high_risk_insufficient_context_abstains() -> None:
    sig = SufficiencySignals(proposes_broad_rewrite=True)
    d = assess(sig, risk_level="high")
    assert d.outcome == Sufficiency.NEED_HUMAN_REVIEW.value
    assert d.recommended_action == "abstain"


def test_sufficient_context_proceeds() -> None:
    sig = SufficiencySignals(referenced_apis=("helper",),
                             defined_symbols=frozenset({"helper"}), retrieval_score=0.9)
    v = answer_or_abstain(sig, risk_level="medium")
    assert v.proceed and v.action == "answer"


def test_low_retrieval_score_needs_more_context() -> None:
    v = answer_or_abstain(SufficiencySignals(retrieval_score=0.2), risk_level="low")
    assert not v.proceed and v.action == "retry_with_repo_map"


def test_extract_signals_flags_undefined_referenced_api() -> None:
    sig = extract_signals(
        issue_text="checkout_total is wrong; it must call apply_house_discount from discounts",
        acceptance_criteria=["total correct"],
        context_text="def checkout_total(price):\n    return price * 0.9\n")
    assert "apply_house_discount" in sig.referenced_apis
    assert "apply_house_discount" in sig.undefined_apis    # not defined in context
    assert "checkout_total" in sig.defined_symbols
