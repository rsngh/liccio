"""Unified skill self-improvement overview (Round 20).

One operator view over the adaptive state: which skills are ACTIVE, what the recent
evolution timeline did, and — the new bit — which scopes are the best NEXT optimization
targets (no skill yet, or an active skill that hasn't improved recently). This turns the
autonomous loop from a black box into a steerable, prioritized backlog.
"""

from __future__ import annotations

from typing import Any

from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.schemas.skill_evolution import SkillEvolutionEvent
from acp.training.skill_improvement import skill_dashboard
from acp.training.skill_registry import list_skills


def next_optimization_targets(
    store: EntityStore, candidate_scopes: list[str], *, top: int = 5,
) -> list[dict]:
    """Rank scopes by optimization priority.

    A scope with NO active skill is highest priority (untapped headroom); a scope whose
    active skill was last only a ``no_op`` is next (it may have plateaued); a scope with a
    recent successful deploy is lowest (recently improved). Returns ranked target records.
    """
    active = {s.scope.key(): s for s in list_skills(store, status=SkillStatus.ACTIVE)}
    events = store.list_by(SkillEvolutionEvent)
    last_action: dict[str, str] = {}
    for e in sorted(events, key=lambda e: e.created_at or ""):
        last_action[e.scope_key] = e.action
    ranked: list[dict] = []
    for scope in candidate_scopes:
        if scope not in active:
            priority, reason = 3, "no active skill (untapped headroom)"
        elif last_action.get(scope) == "no_op":
            priority, reason = 2, "active skill plateaued (last cycle no_op)"
        else:
            priority, reason = 1, "recently improved"
        ranked.append({"scope": scope, "priority": priority, "reason": reason,
                       "active_version": active[scope].version if scope in active else None})
    ranked.sort(key=lambda r: r["priority"], reverse=True)
    return ranked[:top]


def self_improvement_overview(
    store: EntityStore, *, candidate_scopes: list[str] | None = None,
    learned_models: dict[str, Any] | None = None,
) -> dict:
    """Combine skills, learned-model state, and next targets into one view."""
    dash = skill_dashboard(store, recent=10)
    targets = (next_optimization_targets(store, candidate_scopes)
               if candidate_scopes else [])
    return {
        "active_skills": dash["active_skills"],
        "n_active_skills": dash["n_active_skills"],
        "evolution_by_action": dash["evolution_by_action"],
        "recent_skill_events": dash["recent_events"],
        "learned_models": learned_models or {},
        "next_optimization_targets": targets,
    }
