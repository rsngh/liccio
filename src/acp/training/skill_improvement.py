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
class CycleGuardrails:
    """Safety bounds on an autonomous self-improvement cycle (Round 19).

    - ``max_deploys``: cap the blast radius — stop deploying after N this cycle.
    - ``abort_on_contaminated``: skip a scope whose evidence is contaminated (a
      noisy run must never drive a deploy), recording a no_op with the reason.
    """

    max_deploys: int = 3
    abort_on_contaminated: bool = True


@dataclass
class SkillCycleReport:
    cycle_id: str
    n_scopes: int = 0
    n_deployed: int = 0
    n_no_op: int = 0
    n_skipped_contaminated: int = 0
    n_skipped_cap: int = 0
    events: list[dict] = field(default_factory=list)


def run_skill_improvement_cycle(
    store: EntityStore, jobs: list[SkillScopeJob], *, cycle_id: str, backend=None,
    max_steps: int = 5, guardrails: CycleGuardrails | None = None,
) -> SkillCycleReport:
    """Run one governed, guardrailed self-improvement cycle over the scope jobs."""
    from acp.evaluation.measurement_hygiene import build_hygiene_report
    g = guardrails or CycleGuardrails()
    report = SkillCycleReport(cycle_id=cycle_id, n_scopes=len(jobs))
    for job in jobs:
        # Contamination guardrail: never optimize from a noisy run.
        if g.abort_on_contaminated and build_hygiene_report(job.cells).contaminated:
            report.n_skipped_contaminated += 1
            _record(store, report, job, action="no_op", reason="evidence contaminated",
                    cycle_id=cycle_id, res=None)
            continue
        # Deploy-cap guardrail: stop DEPLOYING (not optimizing) past the cap.
        if report.n_deployed >= g.max_deploys:
            report.n_skipped_cap += 1
            _record(store, report, job, action="no_op",
                    reason=f"deploy cap {g.max_deploys} reached", cycle_id=cycle_id,
                    res=None)
            continue
        res = optimize_and_deploy(store, job.base, job.cells, scorer=job.scorer,
                                  proposer=job.proposer, backend=backend,
                                  max_steps=max_steps)
        action = "deployed" if res.deployed else "no_op"
        reason = ("; ".join(res.deployment.blocked_reasons)
                  if not res.deployed else "canary/held-out improvement deployed")
        _record(store, report, job, action=action, reason=reason, cycle_id=cycle_id,
                res=res)
    return report


def _record(store: EntityStore, report: SkillCycleReport, job: SkillScopeJob, *,
            action: str, reason: str, cycle_id: str, res) -> None:
    """Persist a SkillEvolutionEvent and update the cycle report counters."""
    event = SkillEvolutionEvent(
        scope_key=job.base.scope.key(), action=action,
        skill_id=(res.deployment.skill_id if res else None),
        from_version=job.base.version,
        to_version=(res.new_version if res else None),
        base_score=(res.base_score if res else None),
        best_score=(res.best_score if res else None),
        reason=reason, cycle_id=cycle_id)
    store.save(event, extra_index={"scope_key": event.scope_key,
                                   "action": event.action})
    if action == "deployed":
        report.n_deployed += 1
    else:
        report.n_no_op += 1
    report.events.append(event.model_dump(mode="json"))


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
