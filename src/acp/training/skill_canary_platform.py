"""Staged skill canary platform (Alpha 21 WS11).

A single A/B test promotes or rejects; a canary PLATFORM rolls a skill out in stages
(5% -> 25% -> 50% -> 100%), advancing only while every guardrail holds and triggering an
immediate rollback on a regression at any stage. Guardrails cover solve-rate, cost,
measurement quality, harness activation/adherence (HAR/HFR), security findings, and
human-review rate — so a skill that looks good at 5% but degrades at scale is caught.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_STAGES = (0.05, 0.25, 0.50, 1.0)


@dataclass
class CanaryGuardrails:
    max_solve_rate_drop: float = 0.0       # canary must not solve worse than control
    max_cost_spike_ratio: float = 1.5      # canary cost <= control * this
    min_measurement_quality: float = 0.7
    max_har_drop: float = 0.1
    max_hfr_drop: float = 0.1
    max_human_review_rate: float = 0.5
    allow_security_findings: bool = False


@dataclass
class StageMetrics:
    control_solve: float
    canary_solve: float
    control_cost: float
    canary_cost: float
    measurement_quality: float
    control_har: float
    canary_har: float
    control_hfr: float
    canary_hfr: float
    human_review_rate: float = 0.0
    security_findings: int = 0


@dataclass
class StageVerdict:
    stage: float
    decision: str  # advance | rollback
    breaches: list[str] = field(default_factory=list)


def evaluate_stage(stage: float, m: StageMetrics, g: CanaryGuardrails | None = None
                   ) -> StageVerdict:
    """Decide advance vs rollback for one canary stage by checking all guardrails."""
    gr = g or CanaryGuardrails()
    breaches: list[str] = []
    if m.canary_solve < m.control_solve - gr.max_solve_rate_drop - 1e-9:
        breaches.append(f"solve-rate regression {m.canary_solve:.2f}<{m.control_solve:.2f}")
    if m.control_cost > 0 and m.canary_cost > m.control_cost * gr.max_cost_spike_ratio:
        breaches.append(f"cost spike {m.canary_cost:.4f}>{m.control_cost:.4f}*"
                        f"{gr.max_cost_spike_ratio}")
    if m.measurement_quality < gr.min_measurement_quality:
        breaches.append(f"measurement quality {m.measurement_quality:.2f} too low")
    if (m.control_har - m.canary_har) > gr.max_har_drop:
        breaches.append("HAR drop")
    if (m.control_hfr - m.canary_hfr) > gr.max_hfr_drop:
        breaches.append("HFR drop")
    if m.human_review_rate > gr.max_human_review_rate:
        breaches.append("human-review spike")
    if m.security_findings and not gr.allow_security_findings:
        breaches.append(f"{m.security_findings} security finding(s)")
    return StageVerdict(stage=stage, decision="rollback" if breaches else "advance",
                        breaches=breaches)


@dataclass
class CanaryRolloutResult:
    promoted: bool
    final_stage: float
    stages: list[StageVerdict] = field(default_factory=list)
    rollback_reason: str = ""


def run_staged_canary(
    stage_metrics: dict[float, StageMetrics], *, stages=DEFAULT_STAGES,
    guardrails: CanaryGuardrails | None = None,
) -> CanaryRolloutResult:
    """Roll out through the stages; promote only if every stage advances to 100%."""
    result = CanaryRolloutResult(promoted=False, final_stage=0.0)
    for stage in stages:
        m = stage_metrics.get(stage)
        if m is None:
            result.rollback_reason = f"no metrics for stage {stage}"
            return result
        v = evaluate_stage(stage, m, guardrails)
        result.stages.append(v)
        result.final_stage = stage
        if v.decision == "rollback":
            result.rollback_reason = "; ".join(v.breaches)
            return result
    result.promoted = True
    return result


def staged_canary_deploy(
    store, candidate, baseline_skill_id, stage_metrics, *,
    stages=DEFAULT_STAGES, guardrails=None,
):
    """Run a staged canary, persist it, and promote/rollback (Alpha 22 WS15).

    Returns (canary_run, deployment_result). On a clean rollout to 100% the candidate is
    deployed ACTIVE; on a rollback at any stage the candidate is left in advisory
    (CANDIDATE) state and the run is recorded rolled_back. The persisted SkillCanaryRun is
    the audit trail (survives restart, WS13).
    """
    from acp.core.enums import SkillStatus
    from acp.db.repositories import EntityStore
    from acp.schemas.skill_canary_run import SkillCanaryRun, SkillCanaryStageRecord
    from acp.training.skill_deploy import SkillDeploymentResult, deploy_skill

    es = store if isinstance(store, EntityStore) else EntityStore(store)
    rollout = run_staged_canary(stage_metrics, stages=stages, guardrails=guardrails)

    stage_records: list[SkillCanaryStageRecord] = []
    for v in rollout.stages:
        m = stage_metrics.get(v.stage)
        stage_records.append(SkillCanaryStageRecord(
            stage=v.stage,
            canary_n=int(getattr(m, "canary_solve", 0) and 0) or 0,
            canary_successes=0,
            cost=getattr(m, "canary_cost", 0.0) if m else 0.0,
            measurement_quality=getattr(m, "measurement_quality", 1.0) if m else 1.0,
            har=getattr(m, "canary_har", 0.0) if m else 0.0,
            hfr=getattr(m, "canary_hfr", 0.0) if m else 0.0,
            security_findings=getattr(m, "security_findings", 0) if m else 0,
            decision=v.decision, breaches=v.breaches))

    run = SkillCanaryRun(
        scope_key=candidate.scope.key(), candidate_skill_id=candidate.id,
        baseline_skill_id=baseline_skill_id, current_stage=rollout.final_stage,
        stages=stage_records,
        status="promoted" if rollout.promoted else "rolled_back",
        rollback_reason=rollout.rollback_reason)

    if rollout.promoted:
        deployment = deploy_skill(es, candidate, canary_score=1.0, baseline_score=0.0)
        if not deployment.deployed:  # e.g. poison scan blocked it
            run.status = "rolled_back"
            run.rollback_reason = "; ".join(deployment.blocked_reasons)
    else:
        # Leave candidate advisory; do not activate.
        deployment = SkillDeploymentResult(
            deployed=False, scope_key=candidate.scope.key(),
            blocked_reasons=[f"canary rolled back: {rollout.rollback_reason}"])
        es.save(candidate.model_copy(update={"status": SkillStatus.CANDIDATE}),
                extra_index={"scope_key": candidate.scope.key(),
                             "status": SkillStatus.CANDIDATE.value})

    es.save(run, extra_index={"scope_key": run.scope_key, "status": run.status})
    return run, deployment
