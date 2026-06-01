"""Active learning + human review + judge tests (charter §15.3-5)."""

from __future__ import annotations

from acp.core.enums import HumanVerdict
from acp.evaluation.active_learning import ActiveLearningSelector, ALInputs
from acp.evaluation.human_review import HumanReviewService
from acp.evaluation.llm_judges import JudgeInput, default_fake_judges, parse_judge_json
from acp.schemas.human_review import HumanLabel, HumanReviewItem


def test_high_uncertainty_selected() -> None:
    s = ActiveLearningSelector().score(ALInputs(task_id="t", uncertainty=1.0))
    assert s.selected is True


def test_high_risk_selected() -> None:
    s = ActiveLearningSelector().score(ALInputs(task_id="t", business_risk=1.0, uncertainty=0.6))
    assert s.selected is True


def test_low_signal_not_selected() -> None:
    s = ActiveLearningSelector().score(ALInputs(task_id="t", uncertainty=0.1))
    assert s.selected is False


def test_audit_sample_always_selected() -> None:
    s = ActiveLearningSelector().score(ALInputs(task_id="t", uncertainty=0.0, is_audit_sample=True))
    assert s.selected is True


def test_disagreement_selected() -> None:
    s = ActiveLearningSelector().score(
        ALInputs(task_id="t", evaluator_disagreement=1.0, uncertainty=0.5, business_risk=0.5)
    )
    assert s.selected is True


def test_human_review_queue_flow() -> None:
    svc = HumanReviewService()
    item = svc.enqueue(HumanReviewItem(task_id="t", reason="high_risk"))
    assert item in svc.list_open()
    svc.label(item.id, HumanLabel(review_item_id=item.id, task_id="t",
              verdict=HumanVerdict.PASS, score=0.9))
    resolved = svc.resolve(item.id)
    assert resolved.status == "resolved"
    assert resolved not in svc.list_open()
    assert len(svc.labels_for(item.id)) == 1


def test_fake_judges_deterministic_and_parse() -> None:
    inp = JudgeInput(
        task_spec="fix bug", acceptance_criteria=["x"], context_summary="ctx",
        diff="def f(): pass\n# test added", evidence_summary="3 passed",
    )
    judges = default_fake_judges()
    assert len(judges) == 5
    r1 = judges[0].judge(inp)
    r2 = judges[0].judge(inp)
    assert r1.score == r2.score
    assert parse_judge_json('garbage {"score": 0.5} trailing')["score"] == 0.5
