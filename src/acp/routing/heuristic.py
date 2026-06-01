"""Heuristic baseline router (charter §13.2).

Maps task risk/type to a RoutingAction. This is the v1 policy; the bandit and
supervised policies (Phase 8) implement the same RoutingPolicy protocol and can
replace it. Unavailable agents are filtered from candidates.
"""

from __future__ import annotations

from acp.core.enums import AgentKind, RiskLevel, TaskType
from acp.schemas.routing import RoutingAction, RoutingDecision
from acp.schemas.task import Task, TaskClassification

POLICY_VERSION = "heuristic-v1"


def _risk(task: Task, cls: TaskClassification | None) -> RiskLevel:
    r = cls.risk_level if cls else task.risk_level
    return RiskLevel(r) if isinstance(r, str) else r


def _task_type(task: Task, cls: TaskClassification | None) -> TaskType:
    t = cls.task_type if cls else task.task_type
    return TaskType(t) if isinstance(t, str) else t


class HeuristicRouter:
    policy_version = POLICY_VERSION

    def __init__(self, available_agents: list[str] | None = None) -> None:
        # default preference order; filtered against availability
        self.available = available_agents or ["patch", "fake"]

    def _pick_agent(self, prefer: list[str]) -> tuple[AgentKind, str]:
        for name in prefer:
            if name in self.available:
                kind = {
                    "fake": AgentKind.FAKE, "patch": AgentKind.PATCH,
                    "claude": AgentKind.CLAUDE, "codex": AgentKind.CODEX,
                    "openhands": AgentKind.OPENHANDS, "simple_llm": AgentKind.SIMPLE_LLM,
                }.get(name, AgentKind.FAKE)
                return kind, name
        # fallback to first available
        if self.available:
            return AgentKind.FAKE, self.available[0]
        return AgentKind.FAKE, "fake"

    def decide(
        self, task: Task, classification: TaskClassification | None = None
    ) -> RoutingDecision:
        risk = _risk(task, classification)
        ttype = _task_type(task, classification)
        constraints: list[str] = []

        if ttype == TaskType.DOCS or risk == RiskLevel.LOW:
            kind, name = self._pick_agent(["patch", "simple_llm", "fake"])
            strategy, verify, parallelism = "minimal", "standard", 1
        elif risk.requires_human_review():
            kind, name = self._pick_agent(["claude", "patch", "fake"])
            strategy, verify, parallelism = "architecture", "strict", 1
            constraints.append("high_risk_requires_human_review")
        else:  # medium-risk bugfix/feature
            kind, name = self._pick_agent(["claude", "patch", "simple_llm", "fake"])
            strategy = (
                "bug_reproduction" if ttype == TaskType.BUGFIX else "hybrid_keyword_embedding"
            )
            verify, parallelism = "standard", 1

        action = RoutingAction(
            agent_kind=kind,
            agent_name=name,
            context_strategy=strategy,
            verification_policy=verify,
            parallelism=parallelism,
            requires_human_approval=risk.requires_human_review(),
            fallback_policy="fake" if name != "fake" else None,
        )
        return RoutingDecision(
            task_id=task.id,
            policy_version=self.policy_version,
            action=action,
            action_probability=1.0,
            candidate_actions=[action],
            exploration_reason="heuristic deterministic choice",
            constraints_applied=constraints,
        )
