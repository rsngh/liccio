"""Human review queue service (charter §15.4)."""

from __future__ import annotations

from acp.core.time import utcnow
from acp.schemas.human_review import HumanLabel, HumanReviewItem

REVIEW_REASONS = (
    "high_risk",
    "low_evaluator_confidence",
    "objective_ml_disagreement",
    "parallel_agent_disagreement",
    "security_sensitive_diff",
    "large_unexpected_diff",
    "novel_repo_area",
    "new_model_or_policy_canary",
    "post_merge_incident",
    "random_audit_sample",
)


class HumanReviewService:
    """In-memory review queue (DB-backed persistence wired via EntityStore)."""

    def __init__(self) -> None:
        self._items: dict[str, HumanReviewItem] = {}
        self._labels: dict[str, list[HumanLabel]] = {}

    def enqueue(self, item: HumanReviewItem) -> HumanReviewItem:
        self._items[item.id] = item
        return item

    def list_open(self) -> list[HumanReviewItem]:
        return [i for i in self._items.values() if i.status == "open"]

    def get(self, item_id: str) -> HumanReviewItem | None:
        return self._items.get(item_id)

    def label(self, item_id: str, label: HumanLabel) -> HumanLabel:
        if item_id not in self._items:
            raise KeyError(f"no review item {item_id}")
        self._labels.setdefault(item_id, []).append(label)
        return label

    def labels_for(self, item_id: str) -> list[HumanLabel]:
        return self._labels.get(item_id, [])

    def resolve(self, item_id: str) -> HumanReviewItem:
        item = self._items[item_id]
        item.status = "resolved"
        item.resolved_at = utcnow()
        return item
