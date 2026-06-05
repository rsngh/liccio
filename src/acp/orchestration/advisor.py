"""Layered advisor / metacognitive escalation (Alpha 24 area 1).

A cheap executor does the work; a frontier advisor is consulted ONLY when uncertainty,
risk, or stalling demands it (Harvey-style executor+advisor; MetaCogAgent confidence-driven
delegation). The advisor is strictly advisory:

- it CANNOT call tools or edit files — it returns a typed recommendation only;
- its output is never user-facing — it enters the AgentTrace as advice;
- it is budgeted (max calls per task) and NOT consulted on low-risk/easy tasks;
- the executor remains responsible for the committed result.

This module provides the trigger classifier, the call/response contract, the budget, and a
``consult_advisor`` driver with an injectable advisor function (live path uses a frontier
model; tests inject a stub). It is deliberately orchestration-only: no file or tool access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

TRIGGERS = (
    "low_confidence", "repeated_test_failure", "high_risk",
    "verifier_disagreement", "ambiguous_spec",
)
RECOMMENDATIONS = ("continue", "revise_plan", "run_test", "stop", "escalate")


@dataclass
class AdvisorPolicy:
    max_calls_per_task: int = 1
    consult_on_easy: bool = False           # never consult on low-risk easy tasks
    low_confidence_threshold: float = 0.5
    min_failures_to_consult: int = 1        # repeated_test_failure trigger threshold


@dataclass
class ExecutorState:
    """What the executor knows when deciding whether to escalate (no tool access)."""
    task_name: str
    difficulty: str                 # easy | medium | hard
    risk: str = "low"               # low | medium | high
    confidence: float = 1.0
    consecutive_failures: int = 0
    verifier_disagreement: bool = False
    ambiguous_spec: bool = False
    evidence_summary: str = ""
    candidate_options: list = field(default_factory=list)


@dataclass
class AdvisorResponse:
    recommendation: str             # one of RECOMMENDATIONS
    next_steps: list = field(default_factory=list)
    risk: str = "low"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.recommendation not in RECOMMENDATIONS:
            raise ValueError(f"bad recommendation {self.recommendation}")


@dataclass
class AdvisorCall:
    trigger: str
    question: str
    executor_state: str
    evidence_summary: str
    candidate_options: list
    advisor_response: AdvisorResponse | None = None
    cost: float = 0.0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "advisor_response"}
        d["advisor_response"] = (None if self.advisor_response is None
                                 else dict(self.advisor_response.__dict__))
        return d


def classify_trigger(state: ExecutorState, policy: AdvisorPolicy | None = None
                     ) -> str | None:
    """Decide whether (and why) to consult the advisor. None = do not consult.

    High-risk always qualifies. Otherwise we escalate on a genuine stall/ambiguity signal.
    Low-risk *easy* tasks are never escalated unless the policy opts in — the advisor must
    not be wasted on work the executor can clearly handle.
    """
    p = policy or AdvisorPolicy()
    if state.risk == "high":
        return "high_risk"
    if state.difficulty == "easy" and state.risk == "low" and not p.consult_on_easy:
        return None
    if state.verifier_disagreement:
        return "verifier_disagreement"
    if state.consecutive_failures >= p.min_failures_to_consult:
        return "repeated_test_failure"
    if state.ambiguous_spec:
        return "ambiguous_spec"
    if state.confidence < p.low_confidence_threshold:
        return "low_confidence"
    return None


# An advisor function takes the structured call and returns a typed response (no tools).
AdvisorFn = Callable[[AdvisorCall], AdvisorResponse]


@dataclass
class AdvisorBudget:
    max_calls: int = 1
    used: int = 0

    def can_call(self) -> bool:
        return self.used < self.max_calls

    def charge(self) -> None:
        self.used += 1


def consult_advisor(state: ExecutorState, *, advisor_fn: AdvisorFn,
                    budget: AdvisorBudget, policy: AdvisorPolicy | None = None,
                    question: str = "What should the executor do next?",
                    cost: float = 0.0) -> AdvisorCall | None:
    """Consult the advisor iff a trigger fires and budget remains. Returns the call or None.

    The advisor cannot mutate anything: it only fills ``advisor_response``. Cost is charged
    to the budget. A returned None means "no escalation" (executor proceeds on its own).
    """
    trigger = classify_trigger(state, policy)
    if trigger is None or not budget.can_call():
        return None
    call = AdvisorCall(trigger=trigger, question=question,
                       executor_state=f"{state.task_name}/{state.difficulty}/risk={state.risk}",
                       evidence_summary=state.evidence_summary,
                       candidate_options=list(state.candidate_options), cost=cost)
    call.advisor_response = advisor_fn(call)
    budget.charge()
    return call
