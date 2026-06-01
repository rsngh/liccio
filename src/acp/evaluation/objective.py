"""Objective evaluator (charter §15.1).

Turns verification evidence + diff + verdict into an EvaluationResult with the
eight charter scores. Phase 7 layers weak supervision, LLM judges, and active
learning on top; this is the deterministic objective core.
"""

from __future__ import annotations

from acp.core.enums import RiskLevel
from acp.schemas.evaluation import EvaluationResult
from acp.schemas.task import Task
from acp.schemas.workspace import DiffBundle
from acp.verification.aggregate import AggregateVerdict


class ObjectiveEvaluator:
    def evaluate(
        self,
        task: Task,
        attempt_id: str | None,
        verdict: AggregateVerdict,
        diff: DiffBundle | None,
        evidence_ids: list[str] | None = None,
        risk_level: RiskLevel | str | None = None,
    ) -> EvaluationResult:
        risk = risk_level if risk_level is not None else task.risk_level
        if isinstance(risk, str):
            risk = RiskLevel(risk)

        spec_compliance = 1.0 if verdict.passed else 0.0
        regression_risk = 0.0 if verdict.passed else 0.7
        maintainability = max(0.0, 1.0 - verdict.review_burden)

        reasons = list(verdict.reasons)
        requires_human = (
            risk.requires_human_review()
            or verdict.confidence < 0.5
            or verdict.security_risk >= 0.7
            or verdict.review_burden >= 0.7
        )
        if risk.requires_human_review():
            reasons.append("high/critical risk requires human review")
        if verdict.confidence < 0.5:
            reasons.append("low evaluator confidence")

        return EvaluationResult(
            task_id=task.id,
            attempt_id=attempt_id,
            spec_compliance=spec_compliance,
            test_adequacy=verdict.test_adequacy,
            regression_risk=regression_risk,
            security_risk=verdict.security_risk,
            review_burden=verdict.review_burden,
            maintainability=maintainability,
            confidence=verdict.confidence,
            requires_human_review=requires_human,
            reasons=reasons,
            evidence_ids=evidence_ids or [],
        )


def diff_touches_tests(diff: DiffBundle | None) -> bool:
    if diff is None:
        return False
    return any(
        ("test" in f.lower() or f.lower().endswith(("_test.py", ".spec.ts", ".test.ts")))
        for f in diff.changed_files
    )
