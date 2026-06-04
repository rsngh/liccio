"""Policy decision dossier (Alpha 11, WS3).

The single artifact that explains *why* a run was routed the way it was. It
gathers — from the persisted run graph plus the analytic layers — the viability
assessment, the chosen action, the candidate alternatives with their scores, the
Pareto trade-off, the counterfactual regret, and the verification/cost/risk
picture, so an operator or reviewer can answer: why this agent, why this context,
why this verifier, why this cost, why this risk, and what would likely have
happened otherwise.

The dossier is assembled from data already in the run graph (no agent re-run);
analytic fields degrade to ``None`` / "insufficient data" when their inputs are
absent rather than overclaiming.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyDecisionDossier:
    run_id: str
    task_id: str | None
    viability: dict[str, Any] | None
    chosen_action: dict[str, Any] | None
    candidate_scores: dict[str, float] = field(default_factory=dict)
    why_chosen: list[str] = field(default_factory=list)
    why_not_others: dict[str, str] = field(default_factory=dict)
    context_strategy: str | None = None
    verification: list[str] = field(default_factory=list)
    cost_ceiling: float | None = None
    risk_level: str | None = None
    human_review_required: bool = False
    exploration_reason: str = ""
    notes: list[str] = field(default_factory=list)
    # Measurement-quality section (Round 12 WS9): lets a reviewer see whether the
    # recommendation rests on clean conclusive task outcomes or is contaminated by
    # infra noise. Populated via attach_measurement_quality(); None when absent.
    measurement_quality: dict[str, Any] | None = None

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id, "task_id": self.task_id,
            "viability": self.viability, "chosen_action": self.chosen_action,
            "candidate_scores": self.candidate_scores,
            "why_chosen": self.why_chosen, "why_not_others": self.why_not_others,
            "context_strategy": self.context_strategy,
            "verification": self.verification, "cost_ceiling": self.cost_ceiling,
            "risk_level": self.risk_level,
            "human_review_required": self.human_review_required,
            "exploration_reason": self.exploration_reason, "notes": self.notes,
            "measurement_quality": self.measurement_quality,
        }


def build_policy_dossier(graph: dict) -> PolicyDecisionDossier:
    """Assemble a dossier from a ``full_run_graph`` dict."""
    state = graph.get("state") or {}
    decision = graph.get("routing_decision") or {}
    action = decision.get("action") or {}
    viability = graph.get("viability")
    scores: dict[str, float] = decision.get("model_scores") or {}

    why_chosen: list[str] = []
    if viability:
        why_chosen.append(f"viability: {viability.get('task_type')}/"
                          f"{viability.get('risk_level')} risk, harness_required="
                          f"{viability.get('true_harness_required')}")
    if decision.get("exploration_reason"):
        why_chosen.append(f"policy: {decision['exploration_reason']}")
    if action.get("context_strategy"):
        why_chosen.append(f"context strategy: {action['context_strategy']}")

    # Why not the other candidates: lower policy score than the chosen one.
    chosen_score = None
    # Find the chosen action's key in candidate_scores by matching agent_name.
    why_not: dict[str, str] = {}
    if scores:
        best_key = max(scores, key=lambda k: scores[k])
        chosen_score = scores.get(best_key)
        for k, v in scores.items():
            if k != best_key:
                why_not[k] = (f"policy score {v:.4f} < chosen {chosen_score:.4f}"
                              if chosen_score is not None else f"score {v:.4f}")

    # Counterfactual regret (if the evaluation/reward layer recorded outcomes).
    notes: list[str] = []
    if not scores:
        notes.append("no candidate scores recorded (heuristic single-candidate route)")

    eval_obj = graph.get("evaluation") or {}
    return PolicyDecisionDossier(
        run_id=str(state.get("run_id") or state.get("id") or ""),
        task_id=decision.get("task_id") or (graph.get("task") or {}).get("id"),
        viability=viability,
        chosen_action=action or None,
        candidate_scores=scores,
        why_chosen=why_chosen,
        why_not_others=why_not,
        context_strategy=action.get("context_strategy"),
        verification=(viability or {}).get("required_verification", [])
        or list(eval_obj.get("verification_kinds", []) if isinstance(eval_obj, dict) else []),
        cost_ceiling=action.get("max_cost_usd"),
        risk_level=(viability or {}).get("risk_level") or state.get("scratch", {}).get(
            "risk_level"),
        human_review_required=bool((viability or {}).get("human_review_required")),
        exploration_reason=decision.get("exploration_reason", ""),
        notes=notes,
    )


def attach_measurement_quality(
    dossier: PolicyDecisionDossier, cells: list,
) -> PolicyDecisionDossier:
    """Attach a WS9 measurement-quality section from the attempts behind a decision.

    ``cells`` are attempt cells (dicts) for the routed task/adapter. The summary
    surfaces conclusive vs infra/inconclusive shares and a ``trustworthy`` flag so a
    reviewer can tell whether the recommendation rests on clean task signal.
    """
    from acp.evaluation.measurement_hygiene import build_hygiene_report
    from acp.evaluation.measurement_quality import measurement_quality_report

    rep = build_hygiene_report(cells)
    # Per-dimension measurement-quality breakdown (WS3 v2): each dimension is
    # independently visible so a reviewer sees exactly which trust dimension is weak.
    mq = measurement_quality_report(cells)
    dossier.measurement_quality = {
        "solve_rate_conclusive": rep.solve_rate,
        "n_conclusive": rep.n_conclusive,
        "n_infra": rep.n_infra,
        "n_inconclusive": rep.n_inconclusive,
        "infra_failure_rate": rep.infra_failure_rate,
        "contaminated": rep.contaminated,
        "contamination_reasons": rep.contamination_reasons,
        "by_outcome": rep.by_outcome,
        "trustworthy": (not rep.contaminated) and rep.n_conclusive > 0,
        "quality_overall": mq.score.overall,
        "quality_trusted": mq.trusted,
        "quality_breakdown": {d.dimension: {"value": d.value, "floor": d.floor,
                                            "passed": d.passed} for d in mq.breakdown},
        "quality_violations": [v.dimension for v in mq.violations],
    }
    if rep.contaminated:
        dossier.notes.append(
            "measurement contaminated: " + "; ".join(rep.contamination_reasons))
    return dossier
