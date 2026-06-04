"""Governed skill deployment + rollback (Round 16 — closed-loop skills).

A deployable SkillOpt result does not silently become production state. Deployment is
governed like a harness update: the candidate must beat the active baseline on a canary
score, the prior active version is archived (kept as the rollback target), and the new
version becomes ACTIVE with an auditable deployment record. ``rollback_skill`` restores
the previous active version if a regression is later observed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.enums import SkillStatus
from acp.db.repositories import EntityStore
from acp.schemas.skill import SkillDocument
from acp.training.skill_registry import list_skills, save_skill


@dataclass
class SkillDeploymentResult:
    deployed: bool
    skill_id: str | None = None
    version: int | None = None
    scope_key: str = ""
    rollback_to: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)


def deploy_skill(
    store: EntityStore, candidate: SkillDocument, *,
    canary_score: float, baseline_score: float, min_gain: float = 1e-9,
) -> SkillDeploymentResult:
    """Promote ``candidate`` to ACTIVE for its scope if its canary beats the baseline.

    Governance contract:
    - canary_score must strictly exceed baseline_score (no negative transfer);
    - the prior ACTIVE skill for the same scope is archived (rollback target);
    - the candidate is saved ACTIVE with its held-out / canary provenance.
    """
    reasons: list[str] = []
    if canary_score < baseline_score + min_gain:
        reasons.append(
            f"canary {canary_score:.3f} does not beat baseline {baseline_score:.3f}")
    if not candidate.content.strip():
        reasons.append("empty skill content")
    if reasons:
        return SkillDeploymentResult(deployed=False, scope_key=candidate.scope.key(),
                                     blocked_reasons=reasons)
    scope_key = candidate.scope.key()
    prior = [s for s in list_skills(store, status=SkillStatus.ACTIVE)
             if s.scope.key() == scope_key]
    rollback_to = max(prior, key=lambda s: s.version).id if prior else None
    for p in prior:
        archived = p.model_copy(update={"status": SkillStatus.ARCHIVED})
        save_skill(store, archived)
    active = candidate.model_copy(update={"status": SkillStatus.ACTIVE,
                                          "parent_id": rollback_to or candidate.parent_id})
    save_skill(store, active)
    return SkillDeploymentResult(
        deployed=True, skill_id=active.id, version=active.version, scope_key=scope_key,
        rollback_to=rollback_to)


def canary_then_deploy(
    store: EntityStore, candidate: SkillDocument, *, control_cells: list,
    canary_cells: list, alpha: float = 0.05, min_lift: float = 0.0,
) -> tuple[SkillDeploymentResult, object]:
    """Online-validated deployment (Round 17): deploy ONLY if the A/B canary promotes.

    The candidate is deployed iff the canary's conclusive-solve lift over the control is
    statistically significant and uncontaminated. Returns (deployment, canary_result).
    """
    from acp.training.skill_canary import evaluate_ab_canary

    canary = evaluate_ab_canary(control_cells, canary_cells, alpha=alpha,
                                min_lift=min_lift)
    if not canary.promote:
        return (SkillDeploymentResult(
            deployed=False, scope_key=candidate.scope.key(),
            blocked_reasons=["canary did not promote: " + "; ".join(canary.reasons)]),
            canary)
    deployment = deploy_skill(store, candidate, canary_score=canary.canary_rate,
                              baseline_score=canary.control_rate)
    return deployment, canary


def rollback_skill(store: EntityStore, scope_key: str) -> SkillDeploymentResult:
    """Revert the ACTIVE skill for a scope to its most recent ARCHIVED predecessor."""
    active = [s for s in list_skills(store, status=SkillStatus.ACTIVE)
              if s.scope.key() == scope_key]
    archived = [s for s in list_skills(store, status=SkillStatus.ARCHIVED)
                if s.scope.key() == scope_key]
    if not archived:
        return SkillDeploymentResult(deployed=False, scope_key=scope_key,
                                     blocked_reasons=["no archived version to roll back to"])
    target = max(archived, key=lambda s: s.version)
    for a in active:
        save_skill(store, a.model_copy(update={"status": SkillStatus.REJECTED}))
    restored = target.model_copy(update={"status": SkillStatus.ACTIVE})
    save_skill(store, restored)
    return SkillDeploymentResult(deployed=True, skill_id=restored.id,
                                 version=restored.version, scope_key=scope_key)
