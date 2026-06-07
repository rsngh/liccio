"""Advisor marginal value (GOALS Alpha 43 P2/P7).

Decide whether consulting the read-only advisor is worth its cost: call it only when the
expected uplift in verified-success probability times the value of success exceeds the advisor
call cost (within the task's budget). No-op / low-value advisor calls are flagged as waste.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.finops.marginal_value import marginal_value_of_next_call


@dataclass(frozen=True)
class AdvisorValueDecision:
    should_call: bool
    expected_marginal_value: float
    reason: str


def advisor_marginal_value(*, p_solve_without_advisor: float, p_solve_with_advisor: float,
                           advisor_cost: float, budget_class: str = "normal_bugfix",
                           spend_so_far: float = 0.0) -> AdvisorValueDecision:
    d = marginal_value_of_next_call(
        p_success_now=p_solve_without_advisor, p_success_after=p_solve_with_advisor,
        call_cost=advisor_cost, budget_class=budget_class, spend_so_far=spend_so_far)
    return AdvisorValueDecision(d.proceed, d.expected_marginal_value, d.reason)


def is_advisor_waste(*, solved_without_advisor: bool, solved_with_advisor: bool) -> bool:
    """A consulted advisor that did not change a determinate outcome is waste."""
    return solved_without_advisor == solved_with_advisor
