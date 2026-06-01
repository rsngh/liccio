"""Evaluation pipeline (round-1 two-day D1B6).

Bundles the eval ladder — objective evaluation, weak supervision, LLM judges,
active learning, and adversarial fraud detection — into one reusable unit that
returns an EvaluationBundle. The workflow runner delegates to this so the live
loop uses the full ladder, not just objective eval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.evaluation.active_learning import ActiveLearningScore, ActiveLearningSelector, ALInputs
from acp.evaluation.llm_judges import JudgeInput, LLMJudgeResult, default_fake_judges
from acp.evaluation.objective import diff_touches_tests
from acp.evaluation.weak_supervision import default_supervisor
from acp.schemas.evaluation import EvaluationResult, WeakLabel
from acp.schemas.task import Task, TaskClassification
from acp.schemas.workspace import DiffBundle
from acp.verification.adversarial import Finding, has_high_severity, scan_diff, severity_score
from acp.verification.aggregate import AggregateVerdict


@dataclass
class EvaluationBundle:
    evaluation: EvaluationResult
    weak_label: WeakLabel
    al_score: ActiveLearningScore
    judge_results: list[LLMJudgeResult] = field(default_factory=list)
    adversarial: list[Finding] = field(default_factory=list)
    requires_human_review: bool = False
    reasons: list[str] = field(default_factory=list)


class EvaluationPipeline:
    def __init__(self, judges=None, supervisor=None, al_selector=None) -> None:
        self.judges = judges or default_fake_judges()
        self.supervisor = supervisor or default_supervisor()
        self.al = al_selector or ActiveLearningSelector()

    @staticmethod
    def fraud_features(diff: DiffBundle | None, findings: list[Finding]) -> dict:
        codes = {f.code for f in findings}
        return {
            "deleted_tests": "deleted_test" in codes,
            "weakened_tests": "weakened_assertions" in codes,
            "skip_added": "added_skip" in codes,
            "broad_except": "broad_except" in codes,
            "unrelated_files": "unrelated_churn" in codes,
            "sensitive_files": "security_sensitive_file" in codes,
            "changed_files": len(diff.changed_files) if diff else 0,
        }

    def evaluate(
        self,
        task: Task,
        attempt_id: str | None,
        evaluation: EvaluationResult,
        diff: DiffBundle | None,
        evidence_summaries: list[str],
        verdict: AggregateVerdict | None,
        classification: TaskClassification | None,
    ) -> EvaluationBundle:
        cls = classification
        churn = (diff.insertions + diff.deletions) if diff else 0
        n_files = len(diff.changed_files) if diff else 0

        features = {
            "ci_passed": evaluation.spec_compliance >= 1.0,
            "tests_failed": evaluation.spec_compliance < 1.0,
            "task_type": cls.task_type if cls else None,
            "touches_tests": diff_touches_tests(diff),
            "diff_churn": churn,
            "changed_files": n_files,
            "security_high": evaluation.security_risk >= 0.7,
        }
        weak = self.supervisor.label(features, task_id=task.id, attempt_id=attempt_id)

        judge_input = JudgeInput(
            task_spec=task.title,
            acceptance_criteria=task.acceptance_criteria,
            context_summary="",
            diff=(diff.unified_diff or "") if diff else "",
            evidence_summary="; ".join(evidence_summaries),
        )
        judgements = [j.judge(judge_input) for j in self.judges]
        judge_wants_review = any(j.requires_human_review for j in judgements)

        findings = scan_diff(diff)
        if findings:
            evaluation.review_burden = max(evaluation.review_burden, severity_score(findings))

        disagreement = abs(
            (1.0 if (verdict and verdict.passed) else 0.0)
            - (1.0 if weak.label == "success" else 0.0)
        )
        risk_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(
            str(cls.risk_level) if cls else "medium", 1
        )
        al = self.al.score(ALInputs(
            task_id=task.id, attempt_id=attempt_id,
            uncertainty=1.0 - evaluation.confidence,
            evaluator_disagreement=disagreement,
            business_risk=risk_rank / 3.0,
        ))

        reasons: list[str] = []
        adversarial_review = has_high_severity(findings)
        if findings:
            reasons.extend(f"adversarial:{f.code}:{f.detail}" for f in findings)
        require = bool(
            weak.label in ("needs_review", "failure")
            or judge_wants_review
            or adversarial_review
        )
        if require:
            reasons.append(
                f"weak_label={weak.label}; judges_review={judge_wants_review}; "
                f"adversarial={adversarial_review}"
            )
        if al.selected:
            reasons.append(f"active_learning_priority={al.priority}")

        return EvaluationBundle(
            evaluation=evaluation, weak_label=weak, al_score=al,
            judge_results=judgements, adversarial=findings,
            requires_human_review=require, reasons=reasons,
        )
