"""Dataset factory completion for previously-stubbed kinds (Alpha 8, WS6)."""

from __future__ import annotations

from acp.core.enums import AgentKind, RiskLevel, TaskType
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction, RoutingDecision
from acp.schemas.task import Task
from acp.schemas.trace import AgentTrace
from acp.training.dataset_factory import DatasetFactory, ExhaustBundle


def _bundle() -> ExhaustBundle:
    task = Task(repo_id="r", title="Fix divide by zero in calculator",
                body="divide() returns 0 when b == 0; should raise ZeroDivisionError",
                acceptance_criteria=["divide(x, 0) raises"], task_type=TaskType.BUGFIX,
                risk_level=RiskLevel.MEDIUM)
    action = RoutingAction(agent_kind=AgentKind.CLAUDE, agent_name="claude_harness",
                           context_strategy="test_focused")
    decision = RoutingDecision(task_id=task.id, policy_version="v1", action=action,
                               action_probability=0.7, candidate_actions=[action])
    reward = RewardEvent(task_id=task.id, routing_decision_id=decision.id, reward=1.0,
                         components={"objective": 1.0})
    trace = AgentTrace(attempt_id="att1", task_id=task.id, adapter_name="claude_harness",
                       is_harness=True, status="succeeded", tool_calls=3,
                       changed_files=["calculator.py"], diff_lines=8,
                       input_tokens=500, output_tokens=80, estimated_cost_usd=0.0004)
    return ExhaustBundle(tasks=[task], traces=[trace], routing_decisions=[decision],
                         rewards=[reward])


def test_all_completed_kinds_produce_examples() -> None:
    factory = DatasetFactory()
    bundle = _bundle()
    for kind in ("viability", "context_strategy", "trace_summary", "verification_plan"):
        res = factory.build(kind, bundle)
        assert res.examples, f"{kind} produced no examples"
        assert res.version.n_examples == len(res.examples)
        assert res.leakage.clean
        for ex in res.examples:
            assert ex.dataset_kind == kind


def test_viability_label_reflects_trace_success() -> None:
    res = DatasetFactory().build("viability", _bundle())
    ex = res.examples[0]
    assert ex.target["viable"] is True
    assert ex.inputs["task_type"] in ("bugfix", TaskType.BUGFIX)


def test_context_strategy_carries_reward_and_strategy() -> None:
    res = DatasetFactory().build("context_strategy", _bundle())
    ex = res.examples[0]
    assert ex.target["context_strategy"] == "test_focused"
    assert ex.target["reward"] == 1.0


def test_verification_plan_derived_from_classifier() -> None:
    res = DatasetFactory().build("verification_plan", _bundle())
    ex = res.examples[0]
    assert "required_verification_kinds" in ex.target


def test_trace_summary_is_templated_string() -> None:
    res = DatasetFactory().build("trace_summary", _bundle())
    ex = res.examples[0]
    assert isinstance(ex.target, str)
    assert "claude_harness" in ex.target and "succeeded" in ex.target
