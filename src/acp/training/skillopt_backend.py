"""SkillOpt backend adapters + the governed optimization loop (Alpha 15 WS3/WS5).

A *backend* owns the held-out validation GATE — the SkillOpt rule that a candidate
skill is accepted only if it beats the current/best on held-out score. Two backends:

* :class:`MicrosoftSkillOptBackend` — delegates to the installed ``skillopt`` library
  (``skillopt.evaluation.evaluate_gate``); ``available()`` is False when not installed.
* :class:`ACPInternalSkillOptBackend` — a pure-Python gate with identical semantics, so
  the loop and its tests run with no external dependency.

:func:`optimize_skill` is the governed loop: propose bounded edits from TRUSTED train
evidence, apply them, score the candidate on held-out, gate, keep the best — and refuse
to deploy a result that regresses below the baseline (negative-transfer guard).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from acp.core.optional import try_import
from acp.schemas.skill import SkillDocument
from acp.training.skill_dataset import SkillDataset, SkillTask
from acp.training.skill_edit import apply_edits, edits_within_bound


@dataclass
class GateDecision:
    action: str  # accept_new_best | accept | reject
    best_skill: str
    best_score: float
    best_step: int


class ACPInternalSkillOptBackend:
    """Pure-Python validation gate with SkillOpt semantics (always available)."""

    name = "acp_internal"

    def available(self) -> bool:
        return True

    def gate(self, *, candidate_skill: str, cand_score: float, current_skill: str,
             current_score: float, best_skill: str, best_score: float, best_step: int,
             global_step: int) -> GateDecision:
        if cand_score > best_score:
            return GateDecision("accept_new_best", candidate_skill, cand_score, global_step)
        if cand_score >= current_score:
            return GateDecision("accept", best_skill, best_score, best_step)
        return GateDecision("reject", best_skill, best_score, best_step)


class MicrosoftSkillOptBackend:
    """Delegates the gate to the installed ``skillopt`` library (WS3)."""

    name = "microsoft_skillopt"

    def available(self) -> bool:
        return try_import("skillopt") is not None

    def gate(self, *, candidate_skill: str, cand_score: float, current_skill: str,
             current_score: float, best_skill: str, best_score: float, best_step: int,
             global_step: int) -> GateDecision:
        skillopt = try_import("skillopt")
        if skillopt is None:  # pragma: no cover - guarded by available()
            raise RuntimeError("skillopt not installed")
        res = skillopt.evaluation.evaluate_gate(
            candidate_skill=candidate_skill, cand_hard=cand_score,
            current_skill=current_skill, current_score=current_score,
            best_skill=best_skill, best_score=best_score, best_step=best_step,
            global_step=global_step)
        return GateDecision(res.action, res.best_skill, res.best_score, res.best_step)


def get_backend(name: str = "acp_internal"):
    """Resolve a backend by name, falling back to the internal one when the
    requested backend is unavailable (with the internal one's name)."""
    if name in ("microsoft_skillopt", "microsoft"):
        b = MicrosoftSkillOptBackend()
        if b.available():
            return b
        return ACPInternalSkillOptBackend()
    return ACPInternalSkillOptBackend()


# A scorer rolls a skill out over held-out tasks and returns a 0..1 validation score.
Scorer = Callable[[str, list[SkillTask]], float]
# A proposer suggests bounded edits from train evidence given the current skill.
Proposer = Callable[[list[SkillTask], str], list]


@dataclass
class SkillOptimizationRun:
    base_score: float
    best_score: float
    best_content: str
    accepted: int = 0
    rejected: int = 0
    steps: int = 0
    backend: str = ""
    history: list[dict] = field(default_factory=list)
    deployable: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def improved(self) -> bool:
        return self.best_score > self.base_score


def optimize_skill(
    base: SkillDocument, dataset: SkillDataset, *, scorer: Scorer, proposer: Proposer,
    backend=None, max_steps: int = 5,
) -> SkillOptimizationRun:
    """Run the governed SkillOpt loop and return the result.

    Held-out score is the gate currency; only edits that beat the best-so-far are
    kept as a new best. The result is ``deployable`` only if it strictly improved on
    the baseline (negative-transfer guard) and respected the per-step edit bound.
    """
    be = backend or ACPInternalSkillOptBackend()
    current = best = base.content
    base_score = scorer(base.content, dataset.held_out)
    current_score = best_score = base_score
    best_step = 0
    run = SkillOptimizationRun(base_score=round(base_score, 4), best_score=round(base_score, 4),
                               best_content=best, backend=be.name)
    for step in range(1, max_steps + 1):
        run.steps = step
        edits = proposer(dataset.train, current)
        if not edits:
            run.notes.append(f"step {step}: no edits proposed")
            continue
        if not edits_within_bound(edits):
            run.rejected += 1
            run.notes.append(f"step {step}: edit set exceeds bound, rejected")
            continue
        candidate = apply_edits(current, edits)
        cand_score = scorer(candidate, dataset.held_out)
        decision = be.gate(
            candidate_skill=candidate, cand_score=cand_score, current_skill=current,
            current_score=current_score, best_skill=best, best_score=best_score,
            best_step=best_step, global_step=step)
        run.history.append({
            "step": step, "cand_score": round(cand_score, 4), "action": decision.action,
            "edits": [{"op": getattr(e, "op", "append"),
                       "content": getattr(e, "content", ""),
                       "target": getattr(e, "target", "")} for e in edits]})
        if decision.action == "accept_new_best":
            best, best_score, best_step = candidate, cand_score, step
            current, current_score = candidate, cand_score
            run.accepted += 1
        elif decision.action == "accept":
            current, current_score = candidate, cand_score
            run.accepted += 1
        else:
            run.rejected += 1
    run.best_content = best
    run.best_score = round(best_score, 4)
    # Negative-transfer guard: deploy only on a strict held-out improvement.
    run.deployable = best_score > base_score + 1e-9
    if not run.deployable:
        run.notes.append("not deployable: no held-out improvement over baseline")
    return run


def next_version(base: SkillDocument, run: SkillOptimizationRun) -> SkillDocument:
    """Produce the next SkillDocument version from a deployable run (lineage + score)."""
    return SkillDocument(
        name=base.name, content=run.best_content, scope=base.scope,
        version=base.version + 1, parent_id=base.id, status=base.status,
        held_out_score=run.best_score, provenance=base.provenance,
        rationale=f"skillopt {run.backend}: {run.base_score} -> {run.best_score} "
                  f"({run.accepted} accepted / {run.rejected} rejected)")
