"""Production shadow mode (Alpha 26): recommend, never write.

Shadow mode runs ACP on real tasks in OBSERVE-ONLY form: it recommends a route (adapter),
a compute arm, and an answer/abstain action, attaches a policy dossier (the evidence behind
the recommendation), and records whether a human accepted it and what actually happened —
WITHOUT any autonomous write. This gathers real-task evidence at zero execution risk, and is
the bridge from "trustworthy on benchmarks" to "trustworthy on real work."

A ShadowDecision composes the existing governance pieces: the abstention gate (is the
evidence sufficient to act?), the capability matrix (which adapter, with what CI?), and the
compute-escalation policy (which compute arm pays off?). ``autonomous_write`` is always
False — the invariant that makes shadow mode safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.orchestration.abstention import EvidenceSignals, decide
from acp.orchestration.compute_policy import choose_arm


@dataclass
class TaskContext:
    task_id: str
    task_type: str
    risk: str = "low"
    difficulty: str = "easy"
    repo_type: str = "unknown"
    spec_clarity: float = 1.0
    context_coverage: float = 1.0
    self_confidence: float = 1.0
    single_shot_reliability: float = 1.0
    has_tests: bool = True


@dataclass
class ShadowDecision:
    task_id: str
    action: str                         # answer | abstain | ask_for_spec | ...
    recommended_adapter: str | None
    recommended_compute_arm: str
    adapter_ci: list = field(default_factory=list)   # [low, high] Wilson CI of the cell
    rationale: str = ""
    dossier: dict = field(default_factory=dict)
    autonomous_write: bool = False      # INVARIANT: shadow mode never writes

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def recommend(ctx: TaskContext, *, matrix=None) -> ShadowDecision:
    """Produce a recommend-only decision + dossier for a task. Never writes."""
    # 1. Abstention gate: is the evidence sufficient to act at all?
    sig = EvidenceSignals(spec_clarity=ctx.spec_clarity,
                          context_coverage=ctx.context_coverage,
                          self_confidence=ctx.self_confidence, risk=ctx.risk,
                          has_reproduction=ctx.has_tests, test_present=ctx.has_tests)
    gate = decide(sig)

    # 2. Capability matrix: which adapter, and with what confidence?
    adapter = None
    ci: list = []
    matrix_reason = "no matrix provided"
    if matrix is not None:
        cell, matrix_reason = matrix.best_for(ctx.task_type, ctx.risk, ctx.repo_type)
        if cell is not None:
            adapter = cell.agent_class
            ci = [cell.success_rate_ci_low, cell.success_rate_ci_high]

    # 3. Compute-escalation policy: which arm pays off given reliability + stakes?
    arm = choose_arm(single_shot_reliability=ctx.single_shot_reliability, risk=ctx.risk,
                     value=0.6)

    action = "answer" if gate.action == "answer" else gate.action
    rationale = (f"{matrix_reason}; compute={arm.reason}; gate={gate.reason}")
    dossier = {
        "task_type": ctx.task_type, "risk": ctx.risk, "difficulty": ctx.difficulty,
        "abstention": gate.to_dict(),
        "adapter_choice": {"adapter": adapter, "ci": ci, "reason": matrix_reason},
        "compute_arm": arm.to_dict(),
        "evidence_sufficient": gate.action == "answer",
    }
    return ShadowDecision(
        task_id=ctx.task_id, action=action, recommended_adapter=adapter,
        recommended_compute_arm=arm.arm, adapter_ci=ci, rationale=rationale,
        dossier=dossier, autonomous_write=False)


@dataclass
class ShadowRun:
    decision: ShadowDecision
    human_verdict: str | None = None    # accepted | rejected | None
    observed_outcome: str | None = None  # solved | failed | None

    def to_dict(self) -> dict:
        return {"decision": self.decision.to_dict(), "human_verdict": self.human_verdict,
                "observed_outcome": self.observed_outcome}


def production_shadow_report(runs: list) -> dict:
    """Aggregate shadow runs: acceptance, abstention, and zero-write invariant proof."""
    n = len(runs)
    accepted = sum(1 for r in runs if r.human_verdict == "accepted")
    rejected = sum(1 for r in runs if r.human_verdict == "rejected")
    abstained = sum(1 for r in runs if r.decision.action != "answer")
    # every recommendation must carry a dossier and must NOT write
    all_have_dossier = all(r.decision.dossier for r in runs)
    no_writes = all(not r.decision.autonomous_write for r in runs)
    return {"experiment": "production_shadow", "n_runs": n,
            "n_accepted": accepted, "n_rejected": rejected, "n_abstained": abstained,
            "acceptance_rate": round(accepted / n, 4) if n else 0.0,
            "every_recommendation_has_dossier": all_have_dossier,
            "no_autonomous_writes": no_writes,
            "runs": [r.to_dict() for r in runs]}
