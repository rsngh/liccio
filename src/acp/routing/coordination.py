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
    skill_id: str | None = None        # primary skill (back-compat)
    skill_version: int | None = None
    selected_skills: list[dict] = field(default_factory=list)  # composed skill set (WS8)
    rejected_skills: dict[str, str] = field(default_factory=dict)
    composed_skill: str = ""           # the composed skill document content
    rationale: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "task_type": self.task_type, "risk_level": self.risk_level,
            "agent_name": self.agent_name, "topology": self.topology,
            "skill_id": self.skill_id, "skill_version": self.skill_version,
            "selected_skills": self.selected_skills,
            "rejected_skills": self.rejected_skills,
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

    # 3) Skill SET — compose the active skill library applicable to this scope (WS8).
    skill_id = skill_version = None
    selected: list[dict] = []
    rejected: dict[str, str] = {}
    composed = ""
    if store is not None:
        from acp.core.enums import SkillStatus
        from acp.training.skill_composition import compose_skills
        from acp.training.skill_negative_transfer import applies_to_domain
        from acp.training.skill_registry import list_skills
        # Exclude skills that showed negative transfer on this task type (WS10).
        applicable = [s for s in list_skills(store, status=SkillStatus.ACTIVE)
                      if s.scope.matches(task_type=task_type, risk_level=risk_level,
                                         harness=agent_name)
                      and applies_to_domain(s, task_type)]
        if applicable:
            comp = compose_skills(applicable, risk_level=risk_level)
            composed = comp.content
            selected, rejected = comp.included, comp.excluded
            if selected:
                skill_id = selected[0]["skill_id"]
                skill_version = selected[0]["version"]
            rationale["skill"] = (
                f"composed {len(selected)} skill(s), {len(rejected)} rejected, "
                f"{comp.conflicts_resolved} conflicts resolved, ~{comp.token_estimate} tok")
        else:
            rationale["skill"] = "no active skill for scope"

    return CoordinationDecision(
        task_type=task_type, risk_level=risk_level, agent_name=agent_name,
        topology=topology, skill_id=skill_id, skill_version=skill_version,
        selected_skills=selected, rejected_skills=rejected, composed_skill=composed,
        rationale=rationale)
