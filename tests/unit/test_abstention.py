"""Selective abstention / sufficient-context gate (Alpha 24 area 9)."""

from __future__ import annotations

import pytest

from acp.orchestration.abstention import (
    AbstentionPolicy,
    EvidenceSignals,
    decide,
    evidence_adequacy,
)


def test_clear_well_evidenced_task_answers() -> None:
    d = decide(EvidenceSignals(spec_clarity=0.9, context_coverage=0.9, self_confidence=0.9))
    assert d.action == "answer" and d.sufficient_context


def test_ambiguous_spec_asks_first() -> None:
    d = decide(EvidenceSignals(spec_clarity=0.2, context_coverage=0.9, self_confidence=0.9))
    assert d.action == "ask_for_spec"  # cheapest fix takes precedence


def test_low_coverage_retrieves_more() -> None:
    d = decide(EvidenceSignals(spec_clarity=0.9, context_coverage=0.3, self_confidence=0.9))
    assert d.action == "retrieve_more"


def test_high_risk_low_confidence_consults_advisor() -> None:
    d = decide(EvidenceSignals(spec_clarity=0.9, context_coverage=0.9, self_confidence=0.5,
                               risk="high"))
    assert d.action == "consult_advisor"


def test_no_proof_signal_abstains_or_discovers() -> None:
    low = decide(EvidenceSignals(spec_clarity=0.9, context_coverage=0.9, self_confidence=0.9,
                                 has_reproduction=False, test_present=False))
    assert low.action == "abstain"
    high = decide(EvidenceSignals(spec_clarity=0.9, context_coverage=0.9, self_confidence=0.9,
                                  has_reproduction=False, test_present=False, risk="high"))
    assert high.action == "run_discovery_task"
    # no proof signal caps adequacy regardless of other strong signals
    assert low.evidence_adequacy <= 0.4


def test_low_confidence_with_evidence_abstains() -> None:
    d = decide(EvidenceSignals(spec_clarity=0.9, context_coverage=0.9, self_confidence=0.2))
    assert d.action == "abstain"


def test_adequacy_is_weakest_link() -> None:
    assert evidence_adequacy(
        EvidenceSignals(spec_clarity=0.9, context_coverage=0.3, self_confidence=0.8)) == 0.3


def test_bad_action_rejected() -> None:
    from acp.orchestration.abstention import AbstentionDecision
    with pytest.raises(ValueError):
        AbstentionDecision("guess", "x", 0.5, True)


def test_high_risk_needs_more_coverage() -> None:
    sig = EvidenceSignals(spec_clarity=0.9, context_coverage=0.6, self_confidence=0.9)
    assert decide(sig).action == "answer"                       # ok at low risk
    sig.risk = "high"
    assert decide(sig, AbstentionPolicy()).action == "retrieve_more"  # stricter at high risk
