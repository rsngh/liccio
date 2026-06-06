"""Learned + ensemble viability (WS2) and context-strategy learner (WS3)."""

from __future__ import annotations

import pytest

from acp.core.classifier import classify
from acp.core.enums import RiskLevel
from acp.core.viability_learned import (
    EnsembleViabilityAssessor,
    LearnedViabilityAssessor,
    evaluate_learned_viability,
    viability_features,
)
from acp.routing.context_strategy_learner import (
    ContextStrategyPolicy,
    ContextStrategyPredictor,
    evaluate_context_strategy_predictor,
)
from acp.schemas.task import Task


def _case(title: str, body: str, viable: bool, **kw):
    task = Task(repo_id="r", title=title, body=body, **kw)
    return {"task": task, "cls": classify(task), "viable": viable}


def _dataset():
    cases = []
    for i in range(12):
        cases.append(_case(f"Fix bug in parser {i}", "parser.py crashes on input",
                           viable=True, acceptance_criteria=["parses"]))
    for i in range(12):
        cases.append(_case(f"do vague thing {i}", "", viable=False))
    return cases


def _rows(cases):
    return [{**viability_features(c["task"], c["cls"]),
             "viable": 1 if c["viable"] else 0} for c in cases]


def test_learned_assessor_predicts_in_range_and_separates() -> None:
    pytest.importorskip("sklearn")  # learned assessor needs scikit-learn (data/learning extra)
    cases = _dataset()
    a = LearnedViabilityAssessor()
    a.fit(_rows(cases))
    solvable = [c for c in cases if c["viable"]][0]
    unsolvable = [c for c in cases if not c["viable"]][0]
    ps = a.predict_viable(solvable["task"], solvable["cls"])
    pu = a.predict_viable(unsolvable["task"], unsolvable["cls"])
    assert 0.0 <= ps <= 1.0 and 0.0 <= pu <= 1.0
    assert ps > pu  # solvable scores higher than unsolvable


def test_ensemble_is_advisory_by_default() -> None:
    cases = _dataset()
    learned = LearnedViabilityAssessor()
    learned.fit(_rows(cases))
    ens = EnsembleViabilityAssessor(learned=learned)
    sec = _case("Fix SQL injection in auth", "attacker can inject sql in login",
                viable=False, acceptance_criteria=["blocked"])
    a = ens.assess(sec["task"], sec["cls"])
    # Safety decisions come from the rules and are never relaxed when advisory.
    assert a.true_harness_required is True
    assert a.human_review_required is True
    assert "learned_viable_prob" in a.supporting_features


def test_eval_report_has_metrics_and_promotion_flag() -> None:
    cases = _dataset()
    learned = LearnedViabilityAssessor()
    learned.fit(_rows(cases))
    rep = evaluate_learned_viability(learned, cases)
    d = rep.as_dict()
    for k in ("accuracy", "precision", "recall", "brier", "ece",
              "high_risk_false_negative_rate", "promotable"):
        assert k in d
    assert isinstance(d["promotable"], bool)


def test_context_strategy_predictor_learns_best() -> None:
    # test_focused gets high reward for bugfix; minimal low.
    rows = []
    for _ in range(10):
        rows.append({"task_type": "bugfix", "risk_level": "medium",
                     "context_strategy": "test_focused", "reward": 1.0})
        rows.append({"task_type": "bugfix", "risk_level": "medium",
                     "context_strategy": "minimal", "reward": 0.0})
    pred = ContextStrategyPredictor()
    pred.fit(rows)
    ranked = pred.rank("bugfix", "medium", ["test_focused", "minimal"])
    assert ranked[0][0] == "test_focused"
    acc = evaluate_context_strategy_predictor(pred, rows)
    assert acc["top1_accuracy"] == 1.0


def test_context_strategy_policy_cold_start_default() -> None:
    pol = ContextStrategyPolicy()
    assert pol.choose("bugfix", "medium") == "hybrid_keyword_embedding"


def test_high_risk_fn_gates_promotion() -> None:
    # A degenerate "always viable" model -> high-risk false negatives -> not promotable.
    class AlwaysViable(LearnedViabilityAssessor):
        def predict_viable(self, task, cls):
            return 1.0

    sec = _case("Fix SQL injection", "sql injection in login", viable=False,
                acceptance_criteria=["blocked"])
    sec["cls"] = sec["cls"].model_copy(update={"risk_level": RiskLevel.HIGH})
    rep = evaluate_learned_viability(AlwaysViable(), [sec])
    assert rep.high_risk_false_negative_rate > 0.0
    assert rep.promotable is False
