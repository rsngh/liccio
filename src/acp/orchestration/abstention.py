"""Selective abstention / sufficient-context gate (Alpha 24 area 9).

Selective-RAG finding: *sufficient context is not enough* — a model can hallucinate even
when the context suffices, so generation should combine a self-confidence signal with a
sufficient-context autorater and ABSTAIN (or acquire more evidence / a spec) when either is
weak. For a coding agent this prevents a vague or under-evidenced task from entering
implementation, where a confident-but-wrong patch is expensive.

The gate maps evidence signals to one typed action:

    answer | ask_for_spec | retrieve_more | consult_advisor | run_discovery_task | abstain

Measurement-trust: an abstention is recorded as INCONCLUSIVE (the system declined), never a
capability failure — so abstaining can only improve the bad-patch rate, never the solve
rate of attempts it actually made. Decisions are OPE-evaluable (each carries the signals).
"""

from __future__ import annotations

from dataclasses import dataclass

ACTIONS = ("answer", "ask_for_spec", "retrieve_more", "consult_advisor",
           "run_discovery_task", "abstain")


@dataclass
class EvidenceSignals:
    spec_clarity: float = 1.0        # 0..1 how unambiguous the task spec is
    context_coverage: float = 1.0    # 0..1 fraction of needed context retrieved
    self_confidence: float = 1.0     # 0..1 model's own confidence
    risk: str = "low"                # low | medium | high
    has_reproduction: bool = True    # is there a failing test / repro to verify against
    test_present: bool = True        # are there tests to provide a proof signal


@dataclass
class AbstentionPolicy:
    min_spec_clarity: float = 0.5
    min_context_coverage: float = 0.5
    min_self_confidence: float = 0.4
    # High-risk tasks demand stronger evidence before answering.
    high_risk_min_coverage: float = 0.7
    high_risk_min_confidence: float = 0.6


@dataclass
class AbstentionDecision:
    action: str
    reason: str
    evidence_adequacy: float         # 0..1 combined adequacy score
    sufficient_context: bool

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"bad action {self.action}")

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def evidence_adequacy(s: EvidenceSignals) -> float:
    """Combined adequacy: the weakest links (spec, coverage, confidence) dominate."""
    base = min(s.spec_clarity, s.context_coverage, s.self_confidence)
    # A missing proof signal (no tests/repro) caps adequacy — we cannot verify a patch.
    cap = 1.0 if (s.test_present or s.has_reproduction) else 0.4
    return round(min(base, cap), 4)


def decide(s: EvidenceSignals, policy: AbstentionPolicy | None = None) -> AbstentionDecision:
    """Map evidence signals to a typed answer-or-acquire-or-abstain action.

    Order reflects what is cheapest to fix first: an ambiguous spec is asked about before we
    spend retrieval; high-risk under-evidence escalates to discovery/advisor rather than
    guessing; genuinely weak evidence with no cheap remedy abstains.
    """
    p = policy or AbstentionPolicy()
    adequacy = evidence_adequacy(s)
    min_cov = p.high_risk_min_coverage if s.risk == "high" else p.min_context_coverage
    min_conf = p.high_risk_min_confidence if s.risk == "high" else p.min_self_confidence
    sufficient = (s.context_coverage >= min_cov and (s.test_present or s.has_reproduction))

    if s.spec_clarity < p.min_spec_clarity:
        return AbstentionDecision("ask_for_spec", "ambiguous spec", adequacy, sufficient)
    if not (s.test_present or s.has_reproduction):
        action = "run_discovery_task" if s.risk == "high" else "abstain"
        return AbstentionDecision(action, "no proof signal (no tests/repro)", adequacy,
                                  sufficient)
    if s.context_coverage < min_cov:
        return AbstentionDecision("retrieve_more", "insufficient context coverage", adequacy,
                                  sufficient)
    if s.risk == "high" and s.self_confidence < min_conf:
        return AbstentionDecision("consult_advisor", "high-risk low-confidence", adequacy,
                                  sufficient)
    if s.self_confidence < p.min_self_confidence:
        return AbstentionDecision("abstain", "low self-confidence with no cheap remedy",
                                  adequacy, sufficient)
    return AbstentionDecision("answer", "evidence adequate", adequacy, sufficient)
