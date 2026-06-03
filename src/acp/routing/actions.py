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


class CandidateGenerator:
    """Generates the routing action space (charter §13.1; round-1 D2B1).

    One candidate per (agent × context strategy × verification policy), seeded
    from a base action shape so risk/budget flags carry through.
    """

    def __init__(
        self,
        strategies: list[str] | None = None,
        verification_policies: list[str] | None = None,
        topologies: list[list[str]] | None = None,
    ) -> None:
        self.strategies = strategies or ["hybrid_keyword_embedding"]
        self.verification_policies = verification_policies or ["standard"]
        # Each entry is a set of topology flags; [] is the default (full) shape.
        # The router learns which workflow shape is best per task class (WS8).
        self.topologies = topologies or [[]]

    def generate(
        self, base: RoutingAction, available_agents: list[str],
        *, task_type: str | None = None, risk_level: str | None = None,
    ) -> list[RoutingAction]:
        # When task context is given, unsafe topology skips are filtered out so a
        # security/high-risk task can never be routed with strict verification or
        # review skipped (WS14 safety gate); cheap skips on low-risk tasks survive.
        from acp.routing.topology_safety import filter_topology

        out: list[RoutingAction] = []
        seen: set[str] = set()
        for name in available_agents:
            kind = _KINDS.get(name, AgentKind.FAKE)
            for strat in self.strategies:
                for vpol in self.verification_policies:
                    for topo in self.topologies:
                        safe_topo = list(topo)
                        if topo and task_type is not None and risk_level is not None:
                            safe_topo, _ = filter_topology(
                                list(topo), task_type, risk_level)
                        cand = base.model_copy(update={
                            "agent_kind": kind, "agent_name": name,
                            "context_strategy": strat, "verification_policy": vpol,
                            "topology": safe_topo,
                        })
                        if cand.key() not in seen:
                            seen.add(cand.key())
                            out.append(cand)
        return out
