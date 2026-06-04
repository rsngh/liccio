"""Evolver budget study (Alpha 21 WS14).

SkillOpt spends a budget (steps / edits / rollouts) per optimization. More budget can mean
a better skill — but with diminishing returns and rising cost. This finds the knee: the
SMALLEST budget that reaches within tolerance of the best observed score, so the autonomous
evolver doesn't burn rollouts for negligible gain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KNEE_TOLERANCE = 0.02  # within this of the best score counts as "good enough"


@dataclass
class BudgetObservation:
    max_steps: int
    best_score: float
    rollout_cost: float       # total $ spent at this budget


@dataclass
class BudgetStudy:
    recommended_max_steps: int
    best_score: float
    knee_score: float
    rationale: str
    frontier: list[dict] = field(default_factory=list)


def analyze_budget(observations: list[BudgetObservation]) -> BudgetStudy:
    """Recommend the smallest budget within KNEE_TOLERANCE of the best score."""
    if not observations:
        return BudgetStudy(0, 0.0, 0.0, "no observations")
    obs = sorted(observations, key=lambda o: o.max_steps)
    best = max(o.best_score for o in obs)
    knee = next((o for o in obs if o.best_score >= best - KNEE_TOLERANCE), obs[-1])
    return BudgetStudy(
        recommended_max_steps=knee.max_steps, best_score=round(best, 4),
        knee_score=round(knee.best_score, 4),
        rationale=(f"smallest budget within {KNEE_TOLERANCE} of best {best:.2f} "
                   f"is {knee.max_steps} steps (score {knee.best_score:.2f}, "
                   f"cost {knee.rollout_cost:.4f})"),
        frontier=[{"max_steps": o.max_steps, "best_score": round(o.best_score, 4),
                   "rollout_cost": round(o.rollout_cost, 4)} for o in obs])
