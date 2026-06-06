"""Skill economy v3 — value ledger + skill market (Alpha 39).

Makes the skill library a living market: skills COMPETE per scope (task_type/risk/vendor/repo)
and are ranked by cost-adjusted conclusive-success LIFT — the only honest measure of a skill's
worth. The value ledger records per-(skill, scope) observations (baseline vs skill solve rate
+ cost), and the market exposes a leaderboard + the winning skill per scope. It is robust
(small samples don't crown a winner) and activation-aware (a degraded/low-activation
observation is untrusted and never sets value) — reusing the round-25/27 lessons.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.routing.cell_statistics import robustly_better

# small extra cost should never flip a real solve-rate difference, only break ties
_COST_WEIGHT = 2.0


@dataclass
class SkillValueObservation:
    skill_id: str
    scope: str                          # e.g. "bugfix/low/claude_code"
    baseline_successes: int
    baseline_n: int
    skill_successes: int
    skill_n: int
    baseline_cost: float = 0.0
    skill_cost: float = 0.0
    activation_rate: float = 1.0

    def solve_lift(self) -> float:
        b = self.baseline_successes / self.baseline_n if self.baseline_n else 0.0
        s = self.skill_successes / self.skill_n if self.skill_n else 0.0
        return round(s - b, 4)

    def cost_adjusted_value(self) -> float:
        return round(self.solve_lift() - _COST_WEIGHT * (self.skill_cost - self.baseline_cost),
                     6)

    def trusted(self, *, min_activation: float = 0.8) -> bool:
        return (self.activation_rate >= min_activation and self.skill_n > 0
                and self.baseline_n > 0)

    def robustly_helps(self) -> bool:
        return self.trusted() and robustly_better(
            self.skill_successes, self.skill_n, self.baseline_successes, self.baseline_n)


class SkillMarket:
    """Skills compete per scope; ranked by cost-adjusted conclusive-success lift."""

    def __init__(self) -> None:
        self._obs: dict[str, dict[str, SkillValueObservation]] = {}  # scope -> skill -> obs

    def record(self, obs: SkillValueObservation) -> None:
        self._obs.setdefault(obs.scope, {})[obs.skill_id] = obs

    def leaderboard(self, scope: str) -> list:
        rows = []
        for skill, o in self._obs.get(scope, {}).items():
            rows.append({"skill_id": skill, "solve_lift": o.solve_lift(),
                         "cost_adjusted_value": o.cost_adjusted_value(),
                         "trusted": o.trusted(), "robustly_helps": o.robustly_helps()})
        # rank: robust helpers first, then by cost-adjusted value
        return sorted(rows, key=lambda r: (r["robustly_helps"], r["cost_adjusted_value"]),
                      reverse=True)

    def best_skill(self, scope: str) -> str | None:
        """The winning skill for a scope: must ROBUSTLY help (else no skill is deployed)."""
        board = self.leaderboard(scope)
        winners = [r for r in board if r["robustly_helps"]]
        return winners[0]["skill_id"] if winners else None

    def summary(self) -> dict:
        scopes = {}
        for scope in self._obs:
            board = self.leaderboard(scope)
            scopes[scope] = {"best_skill": self.best_skill(scope),
                             "n_competitors": len(board), "leaderboard": board}
        return {"experiment": "skill_market", "n_scopes": len(scopes), "scopes": scopes}


@dataclass
class SkillValueLedger:
    """Append-only per-skill value history -> trend + current cost-adjusted value."""
    _history: list = field(default_factory=list)   # list[SkillValueObservation]

    def record(self, obs: SkillValueObservation) -> None:
        self._history.append(obs)

    def history(self, skill_id: str) -> list:
        return [o for o in self._history if o.skill_id == skill_id]

    def current_value(self, skill_id: str) -> float | None:
        hist = self.history(skill_id)
        return hist[-1].cost_adjusted_value() if hist else None

    def is_declining(self, skill_id: str) -> bool:
        """A skill whose value has dropped over its last two observations is staling."""
        hist = self.history(skill_id)
        return (len(hist) >= 2
                and hist[-1].cost_adjusted_value() < hist[-2].cost_adjusted_value())
