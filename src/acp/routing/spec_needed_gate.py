"""Spec-needed gate (GOALS Alpha 42 P5).

A focused pre-flight: an actionable ticket needs either acceptance criteria or tests and an
unambiguous target. When it doesn't, route to ``spec_needed`` (ask the user) instead of letting
an agent guess — the underspecified-ticket failure mode made a first-class decision.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpecVerdict:
    spec_needed: bool
    reasons: list[str]


def spec_needed(*, acceptance_criteria: list[str] | None, has_tests: bool,
                ambiguous_target: bool) -> SpecVerdict:
    reasons: list[str] = []
    if not acceptance_criteria and not has_tests:
        reasons.append("no acceptance criteria and no tests to define done")
    if ambiguous_target:
        reasons.append("ambiguous target — which symbol/file is unclear")
    return SpecVerdict(spec_needed=bool(reasons), reasons=reasons)
