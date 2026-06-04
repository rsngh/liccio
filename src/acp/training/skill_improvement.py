"""Autonomous skill-improvement cycle + dashboard (Round 18).

One governed cycle: for each skill scope with trusted evidence, run the SkillOpt loop and
deploy improvements behind the gate, recording every outcome (deployed / no_op) as a
durable :class:`SkillEvolutionEvent`. The dashboard rolls the timeline + active skills into
a single view so an operator can see what the system has learned and deployed, and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.schemas.skill import SkillDocument
from acp.schemas.skill_evolution import SkillEvolutionEvent
from acp.training.skill_loop import optimize_and_deploy
from acp.training.skill_registry import list_skills


@dataclass
class SkillScopeJob:
    """A per-scope optimization job: the base skill, its trusted cells, and the
    scorer/proposer the SkillOpt loop will use."""

    base: SkillDocument
    cells: list[Any]
    scorer: Any
    proposer: Any


@dataclass
class SkillCycleReport:
    cycle_id: str
    n_scopes: int = 0
    n_deployed: int = 0
    n_no_op: int = 0
    events: list[dict] = field(default_factory=list)


def run_skill_improvement_cycle(
    store: EntityStore, jobs: list[SkillScopeJob], *, cycle_id: str, backend=None,
    max_steps: int = 5,
) -> SkillCycleReport:
    """Run one governed self-improvement cycle over the given scope jobs."""
    report = SkillCycleReport(cycle_id=cycle_id, n_scopes=len(jobs))
    for job in jobs:
        res = optimize_and_deploy(store, job.base, job.cells, scorer=job.scorer,
                                  proposer=job.proposer, backend=backend,
                                  max_steps=max_steps)
        action = "deployed" if res.deployed else "no_op"
        reason = ("; ".join(res.deployment.blocked_reasons)
                  if not res.deployed else "canary/held-out improvement deployed")
        event = SkillEvolutionEvent(
            scope_key=job.base.scope.key(), action=action,
            skill_id=res.deployment.skill_id, from_version=job.base.version,
            to_version=res.new_version, base_score=res.base_score,
            best_score=res.best_score, reason=reason, cycle_id=cycle_id)
        store.save(event, extra_index={"scope_key": event.scope_key,
                                       "action": event.action})
        if res.deployed:
            report.n_deployed += 1
        else:
            report.n_no_op += 1
        report.events.append(event.model_dump(mode="json"))
    return report


def skill_dashboard(store: EntityStore, *, recent: int = 20) -> dict:
    """A unified view: active skills per scope + the recent evolution timeline."""
    active = list_skills(store, status=SkillStatus.ACTIVE)
    events = store.list_by(SkillEvolutionEvent)
    events_sorted = sorted(events, key=lambda e: e.created_at or "", reverse=True)
    by_action: dict[str, int] = {}
    for e in events:
        by_action[e.action] = by_action.get(e.action, 0) + 1
    return {
        "active_skills": [
            {"id": s.id, "scope": s.scope.key(), "version": s.version,
             "held_out_score": s.held_out_score, "tokens": s.token_estimate}
            for s in active],
        "n_active_skills": len(active),
        "evolution_events_total": len(events),
        "evolution_by_action": by_action,
        "recent_events": [
            {"scope": e.scope_key, "action": e.action, "to_version": e.to_version,
             "base_score": e.base_score, "best_score": e.best_score, "reason": e.reason}
            for e in events_sorted[:recent]],
    }
