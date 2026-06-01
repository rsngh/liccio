"""Routing feature extraction (charter §13.5)."""

from __future__ import annotations

import hashlib
from typing import Any

from acp.core.enums import RiskLevel, TaskType
from acp.schemas.task import Task, TaskClassification


def _hash_bucket(value: str, buckets: int = 1000) -> int:
    return int(hashlib.md5(value.encode()).hexdigest(), 16) % buckets  # noqa: S324


class RoutingFeatures(dict):
    """A plain feature dict (subclass for typing clarity)."""


class RoutingFeatureExtractor:
    def extract(
        self,
        task: Task,
        classification: TaskClassification | None = None,
        repo_stats: dict[str, Any] | None = None,
    ) -> RoutingFeatures:
        repo_stats = repo_stats or {}
        cls = classification
        ttype = (cls.task_type if cls else task.task_type)
        risk = (cls.risk_level if cls else task.risk_level)
        ttype = TaskType(ttype) if isinstance(ttype, str) else ttype
        risk = RiskLevel(risk) if isinstance(risk, str) else risk

        f = RoutingFeatures(
            task_type=ttype.value,
            risk_level=risk.value,
            risk_rank=risk.rank,
            ambiguity_score=cls.ambiguity_score if cls else task.ambiguity_score,
            testability_score=cls.testability_score if cls else 0.5,
            repo_id_bucket=_hash_bucket(task.repo_id),
            primary_language=repo_stats.get("primary_language", "python"),
            estimated_files_touched=cls.affected_modules_estimate if cls else 1,
            affected_module_count=cls.affected_modules_estimate if cls else 1,
            module_churn=repo_stats.get("module_churn", 0.0),
            historical_agent_success=repo_stats.get("historical_agent_success", {}),
            prior_failures_in_module=repo_stats.get("prior_failures_in_module", 0),
            test_coverage_estimate=repo_stats.get("test_coverage_estimate", 0.5),
            ci_failure_type=repo_stats.get("ci_failure_type", "none"),
            context_retrieval_confidence=repo_stats.get("context_retrieval_confidence", 0.5),
            model_price_bucket=repo_stats.get("model_price_bucket", "low"),
        )
        return f

    @staticmethod
    def context_key(features: RoutingFeatures) -> str:
        """Compact context key for contextual bandit indexing."""
        return f"{features['task_type']}|{features['risk_level']}"
