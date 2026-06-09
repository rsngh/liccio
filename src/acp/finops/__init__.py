"""Meta-agent FinOps (GOALS Alpha 42 P6): budget classes, marginal value of compute,
policy cost attribution, and a Pareto promotion gate over verified success per dollar."""

from acp.finops.dashboard import FinOpsLedger, SpendRecord
from acp.finops.marginal_value import (
    BUDGET_CLASSES,
    SUCCESS_VALUE,
    MarginalDecision,
    allow_best_of_k,
    budget_for,
    marginal_value_of_next_call,
    success_value,
)
from acp.finops.policy_cost_report import (
    attribute_cost,
    finops_report,
    promotion_decision,
)

__all__ = [
    "BUDGET_CLASSES", "SUCCESS_VALUE", "MarginalDecision", "allow_best_of_k", "budget_for",
    "marginal_value_of_next_call", "success_value", "attribute_cost", "finops_report",
    "promotion_decision", "FinOpsLedger", "SpendRecord",
]
