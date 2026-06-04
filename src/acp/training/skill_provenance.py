"""Build + persist + query SkillOpt provenance (Alpha 21 WS3)."""

from __future__ import annotations

from acp.core.redaction import Redactor
from acp.db.repositories import EntityStore
from acp.schemas.skill import SkillDocument
from acp.schemas.skill_provenance import (
    SkillCandidateRecord,
    SkillEditRecord,
    SkillProvenanceRun,
)
from acp.training.skillopt_backend import SkillOptimizationRun


def build_provenance(
    run: SkillOptimizationRun, base: SkillDocument, *, deployed: bool = False,
    deployed_skill_id: str | None = None, decision_reason: str = "",
) -> SkillProvenanceRun:
    """Construct a durable provenance record from an optimization run.

    Edit content is redacted so the provenance log can never persist a secret a bad
    proposer might have suggested.
    """
    red = Redactor()
    candidates = [
        SkillCandidateRecord(
            step=h.get("step", 0), validation_score=h.get("cand_score", 0.0),
            gate_action=h.get("action", "reject"),
            edits=[SkillEditRecord(op=e.get("op", "append"),
                                   content=red.redact_text(e.get("content", "")),
                                   target=e.get("target", ""))
                   for e in h.get("edits", [])])
        for h in run.history]
    return SkillProvenanceRun(
        skill_name=base.name, scope_key=base.scope.key(), backend=run.backend,
        base_score=run.base_score, best_score=run.best_score, deployable=run.deployable,
        deployed=deployed, candidates=candidates, n_accepted=run.accepted,
        n_rejected=run.rejected, evidence_run_ids=list(base.provenance),
        deployed_skill_id=deployed_skill_id, decision_reason=decision_reason)


def persist_provenance(store: EntityStore, prov: SkillProvenanceRun) -> SkillProvenanceRun:
    store.save(prov, extra_index={"scope_key": prov.scope_key,
                                  "skill_name": prov.skill_name})
    return prov


def trace_skill(store: EntityStore, *, scope_key: str) -> list[SkillProvenanceRun]:
    """All provenance runs for a scope, newest first — the audit trail."""
    runs = store.list_by(SkillProvenanceRun, scope_key=scope_key)
    return sorted(runs, key=lambda r: r.created_at or "", reverse=True)
