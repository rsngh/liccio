"""Answer-or-abstain gate (GOALS Alpha 42 P5).

Turns a :class:`SufficiencyDecision` into a routing verdict: proceed with an attempt, fetch
more context first, ask the user for a spec, or abstain to human review. High-risk work never
proceeds on insufficient context.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.evaluation.context_sufficiency import (
    Sufficiency,
    SufficiencyDecision,
    SufficiencySignals,
    assess,
)


@dataclass
class GateVerdict:
    proceed: bool                 # may we spend agent compute on an attempt now?
    # answer | retry_with_repo_map | ask_user_spec | human_review | abstain
    action: str
    outcome: str
    reasons: list[str]


def answer_or_abstain(signals: SufficiencySignals, *, risk_level: str = "low") -> GateVerdict:
    d: SufficiencyDecision = assess(signals, risk_level=risk_level)
    proceed = d.outcome == Sufficiency.SUFFICIENT.value
    return GateVerdict(proceed=proceed, action=d.recommended_action, outcome=d.outcome,
                       reasons=d.reasons)
