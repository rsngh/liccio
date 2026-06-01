"""Schema round-trip, JSON stability, validation (charter §7.3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from acp import schemas as s


def _sample_pack() -> s.ContextPack:
    return s.ContextPack(
        repo_id="repo_1",
        task_id="task_1",
        snapshot_id="snap_1",
        items=[
            s.ContextItem(kind="file_chunk", path="a.py", content="print(1)", token_estimate=3),
            s.ContextItem(kind="test_chunk", path="t.py", content="assert True", token_estimate=2),
        ],
    )


@pytest.mark.parametrize(
    "model",
    [
        s.Task(repo_id="r", title="t"),
        s.Repository(name="demo"),
        s.RepoSnapshot(repo_id="r", base_commit="abc"),
        _sample_pack(),
        s.RoutingAction(agent_kind="fake", agent_name="fake"),
        s.AgentAttempt(task_id="t", agent_kind="fake", agent_name="fake"),
        s.Evidence(task_id="t", kind="unit_test", name="pytest", status="pass"),
        s.EvaluationResult(task_id="t"),
        s.PolicyVersion(name="p", version="1"),
        s.PostMergeOutcome(task_id="t"),
    ],
)
def test_roundtrip_and_stable_json(model: s.ACPModel) -> None:
    dumped = model.model_dump(mode="json")
    restored = type(model).model_validate(dumped)
    assert restored.canonical_json() == model.canonical_json()


def test_enum_validation_fails() -> None:
    with pytest.raises(ValidationError):
        s.Task(repo_id="r", title="t", task_type="not_a_type")


def test_context_pack_hash_changes_with_content() -> None:
    p1 = _sample_pack()
    h1 = p1.content_hash
    p2 = _sample_pack()
    p2.items[0].content = "print(2)"
    assert p2.content_hash != h1


def test_context_pack_hash_stable_across_ids() -> None:
    a = _sample_pack()
    b = _sample_pack()  # different ids/timestamps, same content
    assert a.content_hash == b.content_hash


def test_routing_decision_requires_probability_in_range() -> None:
    action = s.RoutingAction(agent_kind="fake", agent_name="fake")
    with pytest.raises(ValidationError):
        s.RoutingDecision(task_id="t", policy_version="v1", action=action, action_probability=0.0)
    with pytest.raises(ValidationError):
        s.RoutingDecision(task_id="t", policy_version="v1", action=action, action_probability=1.5)
    ok = s.RoutingDecision(task_id="t", policy_version="v1", action=action, action_probability=0.5)
    assert ok.action_probability == 0.5


def test_reward_event_requires_components() -> None:
    with pytest.raises(ValidationError):
        s.RewardEvent(task_id="t", reward=1.0)
    ok = s.RewardEvent(task_id="t", reward=1.0, components={"task_success": 1.0})
    assert ok.components["task_success"] == 1.0
    ok2 = s.RewardEvent(
        task_id="t", reward=1.0, metadata={"reward_explanation": "manual override"}
    )
    assert ok2.reward == 1.0


def test_context_pack_render_markdown() -> None:
    md = _sample_pack().render_markdown()
    assert "file_chunk" in md
    assert "a.py" in md
