"""Closed-loop skill optimization + deployment (Round 16).

Ties the pieces together: build a TRUSTED dataset from conclusive traces, run the
governed SkillOpt loop, and — only if the result is deployable (strict held-out gain) —
deploy the new version to ACTIVE behind the canary/rollback governance. The returned
record explains what happened end to end, so the whole loop is auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acp.db.repositories import EntityStore
from acp.schemas.skill import SkillDocument
from acp.training.skill_dataset import build_skill_dataset
from acp.training.skill_deploy import SkillDeploymentResult, deploy_skill
from acp.training.skillopt_backend import (
    Proposer,
    Scorer,
    next_version,
    optimize_skill,
)


@dataclass
class SkillLoopResult:
    base_score: float
    best_score: float
    deployable: bool
    deployed: bool
    new_version: int | None
    deployment: SkillDeploymentResult
    excluded_contaminated: int


def optimize_and_deploy(
    store: EntityStore, base: SkillDocument, cells: list[Any], *,
    scorer: Scorer, proposer: Proposer, backend=None, max_steps: int = 5,
) -> SkillLoopResult:
    """Run the full optimize -> validate -> deploy loop and persist the outcome.

    Deployment is governed: it happens only when the optimization is deployable AND the
    deploy gate (canary > baseline) holds, archiving the prior active version.
    """
    dataset = build_skill_dataset(cells)
    run = optimize_skill(base, dataset, scorer=scorer, proposer=proposer,
                         backend=backend, max_steps=max_steps)
    deployment = SkillDeploymentResult(deployed=False, scope_key=base.scope.key(),
                                       blocked_reasons=["optimization not deployable"])
    new_ver = None
    if run.deployable:
        candidate = next_version(base, run)
        new_ver = candidate.version
        deployment = deploy_skill(store, candidate, canary_score=run.best_score,
                                  baseline_score=run.base_score)
    # WS3: persist the provenance graph so every run is traceable (evidence ->
    # candidates/edits -> validation -> promotion decision).
    from acp.training.skill_provenance import build_provenance, persist_provenance
    prov = build_provenance(
        run, base, deployed=deployment.deployed, deployed_skill_id=deployment.skill_id,
        decision_reason=("deployed" if deployment.deployed
                         else "; ".join(deployment.blocked_reasons)))
    persist_provenance(store, prov)
    return SkillLoopResult(
        base_score=run.base_score, best_score=run.best_score, deployable=run.deployable,
        deployed=deployment.deployed, new_version=new_ver, deployment=deployment,
        excluded_contaminated=dataset.excluded_contaminated)
