"""Routing action-space construction (charter §13.1)."""

from __future__ import annotations

from acp.core.enums import AgentKind
from acp.schemas.routing import RoutingAction

_KINDS = {
    "fake": AgentKind.FAKE,
    "patch": AgentKind.PATCH,
    "claude": AgentKind.CLAUDE,
    "codex": AgentKind.CODEX,
    "openhands": AgentKind.OPENHANDS,
    "simple_llm": AgentKind.SIMPLE_LLM,
}


def candidate_actions(
    available_agents: list[str],
    strategies: list[str] | None = None,
) -> list[RoutingAction]:
    strategies = strategies or ["hybrid_keyword_embedding"]
    out: list[RoutingAction] = []
    for name in available_agents:
        kind = _KINDS.get(name, AgentKind.FAKE)
        for strat in strategies:
            out.append(RoutingAction(agent_kind=kind, agent_name=name, context_strategy=strat))
    return out
