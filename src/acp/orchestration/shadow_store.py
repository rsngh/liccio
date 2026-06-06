"""Shadow-decision store + human-feedback -> training data (Alpha 27).

Persists shadow/guarded decisions, queries them (the operator inbox), and converts human
feedback into training examples. The key product idea: when a human OVERRIDES a
recommendation, their choice is a label the routing/compute policy should learn from. An
ACCEPTED recommendation is a positive label; a REJECTED/OVERRIDDEN one is a corrective label
pointing at the human's choice.
"""

from __future__ import annotations

from acp.db.repositories import EntityStore
from acp.schemas.shadow_decision import ShadowDecisionRecord


def save_decision(store: EntityStore, record: ShadowDecisionRecord) -> ShadowDecisionRecord:
    return store.save(record, extra_index={"task_id": record.task_id,
                                           "human_verdict": record.human_verdict})


def record_human_feedback(store: EntityStore, decision_id: str, *, verdict: str,
                          human_choice: str | None = None,
                          observed_outcome: str | None = None
                          ) -> ShadowDecisionRecord | None:
    """Attach a human verdict (accepted/rejected/overridden) + outcome to a decision."""
    rec = store.get(ShadowDecisionRecord, decision_id)
    if rec is None:
        return None
    updated = rec.model_copy(update={"human_verdict": verdict, "human_choice": human_choice,
                                     "observed_outcome": observed_outcome})
    return save_decision(store, updated)


def feedback_to_training(records: list) -> list:
    """Turn human-reviewed decisions into training examples (the human label is the target).

    accepted -> the recommendation was right (label = recommended_adapter, positive).
    rejected/overridden -> the human disagreed (label = human_choice, corrective).
    Unreviewed decisions yield nothing.
    """
    examples: list[dict] = []
    for r in records:
        if r.human_verdict == "accepted":
            examples.append({
                "inputs": {"task_type": r.task_type, "risk": r.risk,
                           "recommended_adapter": r.recommended_adapter},
                "target": r.recommended_adapter, "label_source": "human",
                "polarity": "positive", "decision_id": r.id})
        elif r.human_verdict in ("rejected", "overridden"):
            examples.append({
                "inputs": {"task_type": r.task_type, "risk": r.risk,
                           "recommended_adapter": r.recommended_adapter},
                "target": r.human_choice, "label_source": "human",
                "polarity": "corrective", "decision_id": r.id})
    return examples


def inbox_summary(records: list) -> dict:
    """Operator-facing summary: counts by verdict + acceptance rate + the zero-write audit."""
    from collections import Counter
    n = len(records)
    by_verdict = Counter((r.human_verdict or "pending") for r in records)
    reviewed = [r for r in records if r.human_verdict is not None]
    accepted = sum(1 for r in records if r.human_verdict == "accepted")
    return {"n_decisions": n, "by_verdict": dict(by_verdict),
            "acceptance_rate": round(accepted / len(reviewed), 4) if reviewed else None,
            "n_training_examples": len(feedback_to_training(records)),
            "no_autonomous_writes": all(not r.autonomous_write for r in records)}
