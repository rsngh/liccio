"""Pareto routing policy + multi-objective profiles (Alpha 9, WS2/WS3/WS4).

Wraps the multi-objective Pareto machinery (`routing/pareto.py`) into a concrete
`RoutingPolicy`: it estimates each candidate action's objective vector
(success/cost/latency/risk) — from an empirical capability matrix when available,
else from the action's own attributes — applies a weight *profile*'s hard
constraints, computes the Pareto frontier, and scalarizes by the profile's weights
to choose. The same candidate set yields different rational choices under
different profiles (cost_saver vs success_max vs risk_min …), and the decision
carries a Pareto explanation for the run graph / review bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.enums import ExplorationMode
from acp.routing.features import RoutingFeatureExtractor
from acp.routing.pareto import ObjectiveVector, pareto_frontier, scalarize
from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction


@dataclass(frozen=True)
class ParetoWeightProfile:
    name: str
    weights: dict[str, float]
    allowed_risk_levels: tuple[str, ...] = ("low", "medium", "high", "critical")
    cost_ceiling: float | None = None
    min_success: float = 0.0
    max_human_review_rate: float | None = None


PROFILES: dict[str, ParetoWeightProfile] = {
    "cost_saver": ParetoWeightProfile(
        "cost_saver", {"success": 0.2, "cost": 0.6, "latency": 0.1, "risk": 0.1},
        cost_ceiling=1.0),
    "balanced": ParetoWeightProfile(
        "balanced", {"success": 0.4, "cost": 0.2, "latency": 0.2, "risk": 0.2}),
    "success_max": ParetoWeightProfile(
        "success_max", {"success": 0.8, "cost": 0.05, "latency": 0.05, "risk": 0.1},
        min_success=0.0),
    "risk_min": ParetoWeightProfile(
        "risk_min", {"success": 0.3, "cost": 0.1, "latency": 0.1, "risk": 0.5},
        allowed_risk_levels=("low", "medium")),
    "latency_min": ParetoWeightProfile(
        "latency_min", {"success": 0.3, "cost": 0.1, "latency": 0.5, "risk": 0.1}),
    "human_review_min": ParetoWeightProfile(
        "human_review_min", {"success": 0.4, "cost": 0.1, "latency": 0.1, "risk": 0.4},
        max_human_review_rate=0.5),
}


def _action_objective(action: RoutingAction) -> ObjectiveVector:
    """Heuristic objective vector from action attributes when no empirical data.

    A true harness is treated as higher success but higher cost/latency; a cheap
    model adapter the reverse. Risk proxied by whether human approval is required.
    """
    name = action.agent_name.lower()
    is_harness = "harness" in name or name in {"claude_agent_sdk", "codex_cli"}
    success = 0.8 if is_harness else 0.55
    cost = float(action.max_cost_usd) * (1.0 if is_harness else 0.3)
    latency = 8.0 if is_harness else 3.0
    risk = 0.3 if action.requires_human_approval else 0.1
    return ObjectiveVector(success=success, cost=cost, latency=latency, risk=risk)


@dataclass
class ParetoRoutingPolicy:
    """A RoutingPolicy that chooses on the Pareto frontier under a weight profile."""

    profile: ParetoWeightProfile = field(default_factory=lambda: PROFILES["balanced"])
    matrix: object | None = None  # optional CapabilityMatrix for empirical objectives
    repo_type: str = "python_package"
    seed: int = 1234

    @property
    def policy_version(self) -> str:
        return f"pareto-{self.profile.name}-v1"

    def _objective(self, action: RoutingAction, ctx_risk: str) -> ObjectiveVector:
        if self.matrix is not None:
            from acp.routing.pareto import cell_objective
            cell, _reason = self.matrix.best_for(  # type: ignore[attr-defined]
                action.agent_kind if isinstance(action.agent_kind, str)
                else action.agent_kind.value, ctx_risk, self.repo_type)
            if cell is not None:
                return cell_objective(cell)
        return _action_objective(action)

    def _allowed(self, action: RoutingAction, vec: ObjectiveVector, ctx_risk: str) -> bool:
        if ctx_risk not in self.profile.allowed_risk_levels:
            return False
        if self.profile.cost_ceiling is not None and vec.cost > self.profile.cost_ceiling:
            return False
        return not vec.success < self.profile.min_success

    def choose_action(
        self, features: dict, candidates: list[RoutingAction]
    ) -> PolicyDecision:
        ctx = RoutingFeatureExtractor.context_key(features)  # type: ignore[arg-type]
        ctx_risk = str(features.get("risk_level", "medium"))
        vecs = {a.key(): self._objective(a, ctx_risk) for a in candidates}
        allowed = [a for a in candidates if self._allowed(a, vecs[a.key()], ctx_risk)]
        pool = allowed or candidates  # never strand the router
        bounds = {
            "success": (min(vecs[a.key()].success for a in pool),
                        max(vecs[a.key()].success for a in pool)),
            "cost": (min(vecs[a.key()].cost for a in pool),
                     max(vecs[a.key()].cost for a in pool)),
            "latency": (min(vecs[a.key()].latency for a in pool),
                        max(vecs[a.key()].latency for a in pool)),
            "risk": (min(vecs[a.key()].risk for a in pool),
                     max(vecs[a.key()].risk for a in pool)),
        }
        frontier = pareto_frontier(pool, key=lambda a: vecs[a.key()])
        scores = {a.key(): scalarize(vecs[a.key()], self.profile.weights, bounds=bounds)
                  for a in frontier}
        chosen = max(frontier, key=lambda a: scores[a.key()])
        return PolicyDecision(
            policy_version=self.policy_version, action=chosen,
            action_probability=max(1e-6, 1.0 / max(1, len(frontier))),
            context_key=ctx, candidate_scores=scores,
            exploration_mode=ExplorationMode.EXPLOIT,
            exploration_reason=f"pareto[{self.profile.name}] frontier={len(frontier)} "
                               f"dominated={len(pool) - len(frontier)}",
            seed=self.seed,
        )

    def observe_reward(self, decision: PolicyDecision, reward: RewardEvent) -> None:
        # Pareto routing is profile-driven, not reward-updated; outcomes inform the
        # capability matrix it consults rather than mutating the policy directly.
        return None


def profile_target(profile_name: str, matrix: object | None = None):
    """An OPE TargetPolicy for a Pareto profile (Alpha 9 WS4): pi(action|ctx)."""
    policy = ParetoRoutingPolicy(profile=PROFILES[profile_name], matrix=matrix)

    def pi(ctx: str, action: str, cands: list[str]) -> float:
        # The profile is deterministic given objective vectors; approximate the
        # propensity as uniform over the candidates it would consider (overlap-safe).
        return 1.0 / len(cands) if cands else 0.0

    # Expose the underlying policy for callers that want richer behavior.
    pi.policy = policy  # type: ignore[attr-defined]
    return pi
