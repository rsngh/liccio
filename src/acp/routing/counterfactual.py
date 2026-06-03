"""Counterfactual what-if analysis (Alpha 9).

OPE estimates the value of a whole *policy*. This is the complementary, per-
*decision* question: "for this specific logged decision, what would each
alternative action have been expected to yield, and how much regret did the
logged choice incur?" It uses the same fitted reward model as the doubly-robust
estimator (a non-parametric per-(context, action) mean) so the counterfactual is
consistent with the OPE machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.routing.ope import OPESample, fit_reward_model


@dataclass
class ActionOutcome:
    action_key: str
    predicted_reward: float
    is_logged_choice: bool

    def as_dict(self) -> dict:
        return {"action_key": self.action_key,
                "predicted_reward": round(self.predicted_reward, 6),
                "is_logged_choice": self.is_logged_choice}


@dataclass
class CounterfactualResult:
    context_key: str
    logged_action: str
    logged_predicted_reward: float
    best_action: str
    best_predicted_reward: float
    regret: float
    outcomes: list[ActionOutcome] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "context_key": self.context_key,
            "logged_action": self.logged_action,
            "logged_predicted_reward": round(self.logged_predicted_reward, 6),
            "best_action": self.best_action,
            "best_predicted_reward": round(self.best_predicted_reward, 6),
            "regret": round(self.regret, 6),
            "outcomes": [o.as_dict() for o in self.outcomes],
        }


def what_if(
    log: list[OPESample],
    context_key: str,
    logged_action: str,
    candidate_keys: list[str],
    *,
    reward_model=None,
) -> CounterfactualResult:
    """Estimate each candidate action's reward in ``context_key`` and the regret
    of the logged action vs the best alternative."""
    q = reward_model or fit_reward_model(log)
    outcomes = [
        ActionOutcome(a, q(context_key, a), a == logged_action) for a in candidate_keys
    ]
    best = max(outcomes, key=lambda o: o.predicted_reward)
    logged_q = q(context_key, logged_action)
    return CounterfactualResult(
        context_key=context_key, logged_action=logged_action,
        logged_predicted_reward=logged_q, best_action=best.action_key,
        best_predicted_reward=best.predicted_reward,
        regret=max(0.0, best.predicted_reward - logged_q),
        outcomes=sorted(outcomes, key=lambda o: o.predicted_reward, reverse=True),
    )


def total_regret(log: list[OPESample]) -> dict:
    """Aggregate counterfactual regret across the whole log: how much reward the
    logged behavior policy left on the table vs always picking the best arm."""
    q = fit_reward_model(log)
    regrets = []
    for s in log:
        best = max(q(s.context_key, a) for a in s.candidates)
        regrets.append(max(0.0, best - q(s.context_key, s.action_key)))
    n = len(regrets) or 1
    return {"n": len(regrets), "mean_regret": round(sum(regrets) / n, 6),
            "max_regret": round(max(regrets), 6) if regrets else 0.0}


def cost_adjusted_regret(log: list[OPESample], costs: list[float], *,
                         cost_weight: float | None = None) -> dict:
    """Counterfactual regret under a cost-aware reward (WS7).

    ``costs[i]`` is the realized $ cost of ``log[i]``. The reward model is refit on
    cost-adjusted rewards (success - cost_weight*cost), so the "best arm" the logged
    policy is compared against is the cost-OPTIMAL one — a cheaper equal-quality
    action is no longer counted as regret-free when a pricier one was chosen.
    """
    from acp.routing.ope import DEFAULT_COST_WEIGHT, OPESample, cost_adjusted_reward

    w = DEFAULT_COST_WEIGHT if cost_weight is None else cost_weight
    adjusted = [
        OPESample(s.context_key, s.action_key, s.behavior_prob,
                  cost_adjusted_reward(s.reward, c, w), s.candidates)
        for s, c in zip(log, costs, strict=True)
    ]
    out = total_regret(adjusted)
    out["cost_weight"] = w
    return out
