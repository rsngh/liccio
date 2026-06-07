"""Context sufficiency judge (GOALS Alpha 42 P5).

Retrieval is not verification. Before spending agent compute, ACP should decide whether the
task is actually solvable with what it has — or whether it must fetch more context, ask the
user for a spec, or abstain to human review. Inspired by SURE-RAG's support/refute/insufficient
framing: an auditable, deterministic decision with explicit reasons, biased to abstain on
high-risk work when evidence is thin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class Sufficiency(str, Enum):
    SUFFICIENT = "sufficient"
    NEED_MORE_CONTEXT = "insufficient_need_more_context"
    NEED_USER_SPEC = "insufficient_need_user_spec"
    NEED_HUMAN_REVIEW = "insufficient_need_human_review"


@dataclass
class SufficiencySignals:
    has_acceptance_criteria: bool = True
    has_tests: bool = True
    referenced_apis: tuple[str, ...] = ()        # APIs the task names that must be defined
    defined_symbols: frozenset[str] = field(default_factory=frozenset)  # symbols in context
    missing_required_files: tuple[str, ...] = ()
    ambiguous_target: bool = False
    conflicting_docs_code: bool = False
    retrieval_score: float = 1.0                 # 0..1; low => weak evidence
    proposes_broad_rewrite: bool = False

    @property
    def undefined_apis(self) -> tuple[str, ...]:
        return tuple(a for a in self.referenced_apis if a not in self.defined_symbols)


@dataclass
class SufficiencyDecision:
    outcome: str                  # Sufficiency value
    # answer | retry_with_repo_map | ask_user_spec | human_review | abstain
    recommended_action: str
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "recommended_action": self.recommended_action,
                "reasons": self.reasons}


def assess(signals: SufficiencySignals, *, risk_level: str = "low") -> SufficiencyDecision:
    """Map signals + risk to a sufficiency outcome and a concrete next action."""
    reasons: list[str] = []
    high_risk = risk_level in ("high", "critical")

    # 1. Spec-level gaps: the task itself is under-specified -> ask the user.
    if not signals.has_acceptance_criteria:
        reasons.append("no acceptance criteria")
    if signals.ambiguous_target:
        reasons.append("ambiguous target symbol")
    if not reasons and not signals.has_tests and high_risk:
        reasons.append("no tests on a high-risk change")
    if not signals.has_acceptance_criteria or signals.ambiguous_target:
        return SufficiencyDecision(Sufficiency.NEED_USER_SPEC.value, "ask_user_spec", reasons)

    # 2. Conflicting evidence -> escalate (advisor/human), don't guess.
    if signals.conflicting_docs_code:
        reasons.append("docs conflict with code")
        action = "human_review" if high_risk else "ask_advisor"
        return SufficiencyDecision(Sufficiency.NEED_HUMAN_REVIEW.value, action, reasons)

    # 3. Missing context the task references -> fetch more (repo_map/grep retry).
    if signals.missing_required_files:
        reasons.append(f"required files missing: {list(signals.missing_required_files)}")
    if signals.undefined_apis:
        reasons.append(f"referenced API(s) not in context: {list(signals.undefined_apis)}")
    if signals.retrieval_score < 0.35:
        reasons.append(f"low retrieval score {signals.retrieval_score}")
    if signals.missing_required_files or signals.undefined_apis or signals.retrieval_score < 0.35:
        return SufficiencyDecision(Sufficiency.NEED_MORE_CONTEXT.value, "retry_with_repo_map",
                                   reasons)

    # 4. High-risk + a broad rewrite proposed on thin evidence -> abstain to human review.
    if high_risk and signals.proposes_broad_rewrite:
        reasons.append("broad rewrite proposed on a high-risk task")
        return SufficiencyDecision(Sufficiency.NEED_HUMAN_REVIEW.value, "abstain", reasons)

    return SufficiencyDecision(Sufficiency.SUFFICIENT.value, "answer", ["context is sufficient"])


def extract_signals(*, issue_text: str, acceptance_criteria: list[str] | None,
                    context_text: str, has_tests: bool = True,
                    retrieval_score: float = 1.0) -> SufficiencySignals:
    """Best-effort signal extraction from a task + the compiled context text (deterministic).

    `referenced_apis` are capitalised or snake/camel identifiers the ISSUE mentions as things to
    *use* (heuristic); `defined_symbols` are identifiers that appear after `def `/`class ` in the
    context. An undefined referenced API means the context lacks its definition.
    """
    defined = set(_IDENT.findall(""))
    for m in re.finditer(r"(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", context_text):
        defined.add(m.group(1))
    # APIs the issue says to use/call (heuristic: identifiers followed by '(' or after 'use/call')
    referenced = set()
    for m in re.finditer(r"\b([a-z_][a-z0-9_]{3,})\s*\(", issue_text):
        referenced.add(m.group(1))
    for m in re.finditer(r"\b(?:use|call|via|from)\s+([a-z_][a-z0-9_]{3,})\b", issue_text):
        referenced.add(m.group(1))
    ambiguous = bool(re.search(r"\b(something|somewhere|the thing|fix it|appropriate)\b",
                               issue_text.lower())) and not acceptance_criteria
    return SufficiencySignals(
        has_acceptance_criteria=bool(acceptance_criteria),
        has_tests=has_tests,
        referenced_apis=tuple(sorted(referenced)),
        defined_symbols=frozenset(defined),
        ambiguous_target=ambiguous,
        retrieval_score=retrieval_score,
    )
