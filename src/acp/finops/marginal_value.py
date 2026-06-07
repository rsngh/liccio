"""Meta-agent FinOps — budget classes + marginal value of compute (GOALS Alpha 42 P6).

The near-term moat is *measured orchestration*: spend the next dollar of agent compute only
when its expected marginal value (extra verified-success probability x value) exceeds its cost,
and let high-risk work justify more spend than docs. Pure functions, no I/O — fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass

# Per-attempt spend ceilings by budget class ($). High-risk work earns a bigger envelope.
BUDGET_CLASSES: dict[str, float] = {
    "cheap_docs": 0.01,
    "normal_bugfix": 0.05,
    "migration": 0.30,
    "high_risk_security": 0.50,
    "incident": 1.00,
    "research_engineering": 0.20,
}
# Value of a verified success by class ($-equivalent) — what we're willing to pay to get it.
SUCCESS_VALUE: dict[str, float] = {
    "cheap_docs": 0.20,
    "normal_bugfix": 2.0,
    "migration": 10.0,
    "high_risk_security": 25.0,
    "incident": 50.0,
    "research_engineering": 8.0,
}


def budget_for(budget_class: str) -> float:
    return BUDGET_CLASSES.get(budget_class, BUDGET_CLASSES["normal_bugfix"])


def success_value(budget_class: str) -> float:
    return SUCCESS_VALUE.get(budget_class, SUCCESS_VALUE["normal_bugfix"])


@dataclass(frozen=True)
class MarginalDecision:
    proceed: bool
    expected_marginal_value: float
    call_cost: float
    reason: str


def marginal_value_of_next_call(*, p_success_now: float, p_success_after: float,
                                call_cost: float, budget_class: str,
                                spend_so_far: float = 0.0) -> MarginalDecision:
    """Decide whether the next (advisor/candidate/retry) call is worth making.

    Expected marginal value = uplift_in_success_probability * value_of_success - call_cost.
    Proceed only if it is positive AND the budget envelope is not exhausted.
    """
    value = success_value(budget_class)
    uplift = max(0.0, p_success_after - p_success_now)
    emv = round(uplift * value - call_cost, 6)
    budget = budget_for(budget_class)
    if spend_so_far + call_cost > budget:
        return MarginalDecision(False, emv, call_cost,
                                f"budget exhausted ({spend_so_far + call_cost:.4f} > {budget})")
    if emv <= 0:
        return MarginalDecision(False, emv, call_cost,
                                f"marginal value {emv} <= 0 (uplift {uplift:.3f} x ${value})")
    return MarginalDecision(True, emv, call_cost, f"marginal value {emv} > 0")


def allow_best_of_k(*, budget_class: str, spend_so_far: float, next_candidate_cost: float,
                    p_success_now: float, p_success_after: float) -> bool:
    """Budget enforcer for best-of-k: stop sampling once the next candidate is not worth it."""
    return marginal_value_of_next_call(
        p_success_now=p_success_now, p_success_after=p_success_after,
        call_cost=next_candidate_cost, budget_class=budget_class,
        spend_so_far=spend_so_far).proceed
