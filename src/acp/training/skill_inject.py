"""Skill-aware context injection (Round 16).

When an ACTIVE skill exists for a routing scope, the orchestrator injects it into the
agent's context so the deployed skill actually takes effect — closing the loop from
"optimized + deployed" to "in force at routing time". The skill is added as a
high-priority context item; lookup respects scope wildcards and prefers the highest
version. No active skill -> the context is returned unchanged.
"""

from __future__ import annotations

from acp.db.repositories import EntityStore
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.skill import SkillDocument
from acp.training.skill_registry import active_skill_for


def active_skill_for_context(
    store: EntityStore, *, task_type: str | None = None, risk_level: str | None = None,
    harness: str | None = None, model_family: str | None = None,
) -> SkillDocument | None:
    """The ACTIVE skill bound to this routing context, if any."""
    return active_skill_for(store, task_type=task_type, risk_level=risk_level,
                            harness=harness, model_family=model_family)


def inject_skill(pack: ContextPack, skill: SkillDocument | None) -> ContextPack:
    """Return a copy of ``pack`` with the skill prepended as a high-priority item.

    No skill -> the original pack is returned unchanged.
    """
    if skill is None or not skill.content.strip():
        return pack
    item = ContextItem(kind="file_chunk", path="SKILL.md",
                       content=f"# Active skill (v{skill.version})\n{skill.content}")
    return pack.model_copy(update={"items": [item, *pack.items]})


def inject_active_skill(
    store: EntityStore, pack: ContextPack, *, task_type: str | None = None,
    risk_level: str | None = None, harness: str | None = None,
    model_family: str | None = None,
) -> tuple[ContextPack, SkillDocument | None]:
    """Look up the active skill for the routing context and inject it. Returns the
    (possibly augmented) pack and the skill that was applied (or None)."""
    skill = active_skill_for_context(store, task_type=task_type, risk_level=risk_level,
                                     harness=harness, model_family=model_family)
    return inject_skill(pack, skill), skill
