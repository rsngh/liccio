"""Unified coordination decision (Round 17 — joint model/topology/skill routing).

AgensFlow argues coordination is more than model choice: it is also the workflow shape
(topology / skip:X) and the procedural skill in force. This composes all three into one
auditable :class:`CoordinationDecision` from the trustworthy evidence each layer owns —
the capability matrix (model), the learned safety-gated topology policy (shape), and the
skill registry (active skill) — with a rationale a reviewer can read end to end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CoordinationDecision:
    task_type: str
    risk_level: str
    agent_name: str | None
    topology: list[str] = field(default_factory=list)
    skill_id: str | None = None
    skill_version: int | None = None
    rationale: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "task_type": self.task_type, "risk_level": self.risk_level,
            "agent_name": self.agent_name, "topology": self.topology,
            "skill_id": self.skill_id, "skill_version": self.skill_version,
            "rationale": self.rationale,
        }


def compose_coordination(
    *, task_type: str, risk_level: str, repo_type: str = "python_package",
    matrix: Any = None, store: Any = None, topology_arms: list | None = None,
    harness_hint: str | None = None,
) -> CoordinationDecision:
    """Compose model + topology + skill into one decision.

    Each layer is optional: with no ``matrix`` the model is the ``harness_hint`` (or
    None); with no ``topology_arms`` the shape is full (no skips); with no ``store`` no
    skill is bound. Every choice records why in ``rationale``.
    """
    rationale: dict[str, str] = {}

    # 1) Model / harness — from the capability matrix's trustworthy best_for.
    agent_name = harness_hint
    if matrix is not None:
        cell, reason = matrix.best_for(task_type, risk_level, repo_type)
        if cell is not None:
            agent_name = cell.agent_class
            rationale["model"] = f"capability matrix: {reason}"
        else:
            rationale["model"] = f"no confident cell ({reason}); hint={harness_hint}"
    elif agent_name:
        rationale["model"] = f"hint {agent_name} (no matrix evidence)"

    # 2) Topology — the cheapest SAFE learned shape (safety gate always applies).
    topology: list[str] = []
    if topology_arms:
        from acp.routing.topology_policy import recommend_topology
        rec = recommend_topology(task_type, risk_level, topology_arms)
        topology = rec.topology
        rationale["topology"] = rec.reason + (
            f"; rejected {sorted(rec.rejected)}" if rec.rejected else "")
    else:
        rationale["topology"] = "full shape (no topology evidence)"

    # 3) Skill — the ACTIVE skill bound to this routing scope.
    skill_id = skill_version = None
    if store is not None:
        from acp.training.skill_registry import active_skill_for
        skill = active_skill_for(store, task_type=task_type, risk_level=risk_level,
                                 harness=agent_name)
        if skill is not None:
            skill_id, skill_version = skill.id, skill.version
            rationale["skill"] = (f"active skill v{skill.version} "
                                  f"(held_out_score={skill.held_out_score})")
        else:
            rationale["skill"] = "no active skill for scope"

    return CoordinationDecision(
        task_type=task_type, risk_level=risk_level, agent_name=agent_name,
        topology=topology, skill_id=skill_id, skill_version=skill_version,
        rationale=rationale)
