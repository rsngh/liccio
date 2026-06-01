"""EvaluationPipeline unit tests (round-1 two-day D1B6)."""

from __future__ import annotations

from acp.evaluation.pipeline import EvaluationPipeline
from acp.schemas.evaluation import EvaluationResult
from acp.schemas.task import Task, TaskClassification
from acp.schemas.workspace import DiffBundle
from acp.verification.aggregate import AggregateVerdict


def _cls(task_type="bugfix", risk="medium") -> TaskClassification:
    return TaskClassification(task_type=task_type, risk_level=risk,
                              ambiguity_score=0.2, testability_score=0.8)


def test_pipeline_returns_full_bundle() -> None:
    task = Task(repo_id="r", title="Fix bug")
    ev = EvaluationResult(task_id=task.id, spec_compliance=1.0, confidence=1.0)
    diff = DiffBundle(unified_diff="+    return a / b\n", changed_files=["m.py"])
    bundle = EvaluationPipeline().evaluate(
        task, "att1", ev, diff, ["pytest:pass"],
        AggregateVerdict(passed=True), _cls(),
    )
    assert bundle.weak_label is not None
    assert len(bundle.judge_results) == 5
    assert bundle.al_score is not None


def test_pipeline_deleted_test_forces_review() -> None:
    task = Task(repo_id="r", title="Fix bug")
    ev = EvaluationResult(task_id=task.id, spec_compliance=1.0, confidence=1.0)
    diff = DiffBundle(unified_diff="-def test_x():\n-    assert True\n",
                      changed_files=["m.py"], deleted_files=["tests/test_x.py"])
    bundle = EvaluationPipeline().evaluate(
        task, "att1", ev, diff, ["pytest:pass"], AggregateVerdict(passed=True), _cls(),
    )
    assert bundle.requires_human_review is True
    assert any("adversarial:deleted_test" in r for r in bundle.reasons)


def test_fraud_features_flags() -> None:
    from acp.verification.adversarial import scan_diff

    diff = DiffBundle(unified_diff="+    pytest.skip('x')\n", changed_files=["t.py"])
    findings = scan_diff(diff)
    feats = EvaluationPipeline.fraud_features(diff, findings)
    assert feats["skip_added"] is True
