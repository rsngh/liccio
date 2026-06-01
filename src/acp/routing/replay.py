"""Learn routing preferences from a multi-harness bakeoff EvalRun (round-4 G).

The bakeoff produces objective per-(task, adapter) outcomes. Replaying those
into the contextual bandit teaches the router which agent to prefer for a given
task class — accounting for both quality (did it solve + verify) and cost. This
closes the loop: the empirical bakeoff directly reshapes future routing.

Replay is idempotent at the EvalRun granularity: applying the same run twice
through a :class:`PolicyReplayer` is a no-op the second time (arms unchanged),
so re-ingesting a report can never double-count.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.enums import AgentKind
from acp.routing.features import RoutingFeatureExtractor
from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction

# Bakeoff cells don't carry a risk level; replay uses a canonical one so the
# learned arms live under a deterministic context key that callers can target.
REPLAY_RISK = "medium"
# Penalty applied per dollar of cost so an equally-good but pricier agent is
# learned to be less preferred.
COST_WEIGHT = 2.0


@dataclass
class PolicyObservation:
    """One (context, action, reward) tuple distilled from an EvalRun cell."""

    context_key: str
    action: RoutingAction
    reward: float
    success: float
    cost_usd: float
    source: str


def replay_context_key(task_type: str) -> str:
    feats = {"task_type": task_type, "risk_level": REPLAY_RISK}
    return RoutingFeatureExtractor.context_key(feats)  # type: ignore[arg-type]


def action_for_adapter(adapter: str) -> RoutingAction:
    """The canonical routing action arm for an adapter (matches replay arms)."""
    return RoutingAction(agent_kind=AgentKind.SIMPLE_LLM, agent_name=adapter)


def _cell_reward(cell: dict) -> tuple[float, float]:
    """(reward, success) for a bakeoff cell: quality minus a cost penalty."""
    if cell.get("success"):
        quality = 1.0
    elif cell.get("verification_pass"):
        quality = 0.5
    else:
        quality = 0.0
    base = cell["reward"] if cell.get("reward") is not None else quality
    reward = base - COST_WEIGHT * float(cell.get("cost_usd", 0.0))
    return reward, (1.0 if cell.get("success") else 0.0)


def observations_from_report(report: dict) -> list[PolicyObservation]:
    """Distil a multi-harness bakeoff report into policy observations."""
    obs: list[PolicyObservation] = []
    for cell in report.get("cells", []):
        reward, success = _cell_reward(cell)
        obs.append(PolicyObservation(
            context_key=replay_context_key(cell["task"]),
            action=action_for_adapter(cell["adapter"]),
            reward=reward, success=success,
            cost_usd=float(cell.get("cost_usd", 0.0)),
            source=cell["name"],
        ))
    return obs


def _scores_snapshot(policy) -> dict[str, dict[str, float]]:
    return {ctx: {k: round(s.mean, 6) for k, s in arms.items()}
            for ctx, arms in getattr(policy, "arms", {}).items()}


@dataclass
class PolicyReplayer:
    """Replays bakeoff EvalRuns into a bandit policy, idempotently per run."""

    policy: object
    applied_runs: set[str] = field(default_factory=set)

    def replay(self, report: dict, *, run_id: str) -> dict:
        if run_id in self.applied_runs:
            return {"applied": False, "run_id": run_id, "reason": "already_applied",
                    "observations": 0, "preference_changes": []}
        before = _scores_snapshot(self.policy)
        observations = observations_from_report(report)
        for o in observations:
            decision = PolicyDecision(
                policy_version=getattr(self.policy, "policy_version", "policy"),
                action=o.action, context_key=o.context_key,
                action_probability=1.0 / max(1, len(observations)))
            reward = RewardEvent(
                task_id="eval", reward=o.reward, label_source="objective",
                components={"quality": o.success, "cost_penalty": -COST_WEIGHT * o.cost_usd},
                metadata={"ctx": o.context_key, "source": o.source})
            self.policy.observe_reward(decision, reward)  # type: ignore[attr-defined]
        self.applied_runs.add(run_id)
        after = _scores_snapshot(self.policy)
        return {
            "applied": True, "run_id": run_id, "observations": len(observations),
            "preference_changes": _preference_changes(before, after),
        }


def _preference_changes(before: dict, after: dict) -> list[dict]:
    changes: list[dict] = []
    for ctx, arms in after.items():
        for k, mean in arms.items():
            prev = before.get(ctx, {}).get(k)
            if prev is None or abs(prev - mean) > 1e-9:
                changes.append({"context": ctx, "action": k,
                                "before": prev, "after": mean})
    return changes
