"""Per-task decision card (Alpha 9 explainable routing)."""

from __future__ import annotations

from acp.core.decision_card import build_decision_card
from acp.routing.capability_matrix import CapabilityMatrix
from acp.schemas.task import Task


def test_card_for_bugfix_recommends_and_explains() -> None:
    task = Task(repo_id="r", title="Fix divide by zero in calculator",
                body="divide() returns 0 when b==0; should raise",
                acceptance_criteria=["divide(x,0) raises"])
    card = build_decision_card(task).as_dict()
    assert card["task_type"] == "bugfix"
    assert card["viable"] is True
    assert card["recommended_context_strategy"] is not None
    assert card["rationale"], "card must explain itself"


def test_card_abstains_on_unspecified_task() -> None:
    task = Task(repo_id="r", title="do something", body="")
    card = build_decision_card(task).as_dict()
    assert card["abstain"] is True
    assert any("ABSTAIN" in r for r in card["rationale"])


def test_card_uses_capability_matrix_when_confident() -> None:
    cells = []
    for i in range(8):
        cells.append({"task_type": "bugfix", "risk": "medium",
                      "adapter": "claude_harness", "is_harness": True,
                      "context_strategy": "test_focused",
                      "success": True, "cost_usd": 0.01, "latency_s": 3.0})
    matrix = CapabilityMatrix.from_bakeoff_report({"cells": cells})
    task = Task(repo_id="r", title="Fix bug in parser", body="parser.py mishandles input",
                acceptance_criteria=["parses"])
    card = build_decision_card(task, matrix=matrix).as_dict()
    # A confident cell drives the recommendation basis.
    assert "confident" in card["recommendation_basis"] or \
        card["recommended_agent_class"] is not None


def test_card_does_not_overclaim_on_low_sample() -> None:
    cells = [{"task_type": "bugfix", "risk": "medium", "adapter": "claude_harness",
              "is_harness": True, "context_strategy": "test_focused",
              "success": True, "cost_usd": 0.01, "latency_s": 3.0}]  # 1 sample
    matrix = CapabilityMatrix.from_bakeoff_report({"cells": cells})
    task = Task(repo_id="r", title="Fix bug", body="x.py broken",
                acceptance_criteria=["works"])
    card = build_decision_card(task, matrix=matrix).as_dict()
    # No overclaim: a 1-sample cell is never the confident basis.
    assert "low_sample" in card["recommendation_basis"] \
        or card["recommendation_basis"] == "no_matching_cells"
