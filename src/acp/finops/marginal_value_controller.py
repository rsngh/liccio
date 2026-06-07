"""Marginal-value controller + provider market (GOALS Alpha 43 P7).

FinOps as a routing objective, not just logging. The controller spends the next unit of agent
compute (an extra candidate, an advisor call, a retry) only while its expected marginal value is
positive within the task's budget. The provider market ranks the FEASIBLE provider set (available
+ contract-passed + uncontaminated + enough cells) by verified success per dollar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.finops.marginal_value import marginal_value_of_next_call


@dataclass
class MarginalValueController:
    budget_class: str = "normal_bugfix"
    spend_so_far: float = 0.0
    steps: list[dict] = field(default_factory=list)

    def should_spend(self, *, p_now: float, p_after: float, step_cost: float, label: str) -> bool:
        d = marginal_value_of_next_call(
            p_success_now=p_now, p_success_after=p_after, call_cost=step_cost,
            budget_class=self.budget_class, spend_so_far=self.spend_so_far)
        self.steps.append({"label": label, "proceed": d.proceed,
                           "emv": d.expected_marginal_value, "reason": d.reason})
        if d.proceed:
            self.spend_so_far = round(self.spend_so_far + step_cost, 6)
        return d.proceed

    def report(self) -> dict:
        return {"budget_class": self.budget_class, "total_spend": self.spend_so_far,
                "n_steps": len(self.steps), "n_proceeded": sum(s["proceed"] for s in self.steps),
                "steps": self.steps}


def feasible_provider_set(providers: list[dict], *, min_conclusive_cells: int = 30) -> list[str]:
    """A provider is FEASIBLE only if available, contract-passed, uncontaminated, and evidenced."""
    out = []
    for p in providers:
        if (p.get("available") and p.get("contract_passed", True)
                and not p.get("contaminated", False)
                and p.get("conclusive_cells", 0) >= min_conclusive_cells):
            out.append(p["provider"])
    return out


def provider_market(providers: list[dict], *, min_conclusive_cells: int = 30) -> dict:
    """Rank the feasible provider set by verified success per dollar; never rank an
    unavailable/under-evidenced provider (its absence is availability evidence, not a verdict)."""
    feasible = feasible_provider_set(providers, min_conclusive_cells=min_conclusive_cells)
    ranked = sorted(
        [p for p in providers if p["provider"] in feasible],
        key=lambda p: (p.get("verified_success_rate", 0.0)
                       / (p.get("cost_per_verified_success") or 1e9)), reverse=True)
    not_measured = {p["provider"]: p.get("reason", "not feasible")
                    for p in providers if p["provider"] not in feasible}
    return {"experiment": "finops_provider_market",
            "feasible_providers": feasible,
            "ranking": [p["provider"] for p in ranked],
            "best_value_provider": ranked[0]["provider"] if ranked else None,
            "potential_savings_not_measured": not_measured,
            "note": "unavailable/under-evidenced providers are reported, never ranked as failures"}
