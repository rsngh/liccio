"""Relative trajectory judge -> preference learning (Alpha 13 WS17)."""

from __future__ import annotations

from acp.evaluation.trajectory_judge import (
    AxisContext,
    preferences_from_same_task_trajectories,
    trace_features,
)
from acp.learning.preference import PreferenceModel
from acp.schemas.trace import AgentTrace


def _trace(**kw) -> AgentTrace:
    base = dict(attempt_id="a", adapter_name="h", is_harness=True, status="succeeded",
                tool_calls=4, file_reads=2, commands=2, changed_files=["x.py"],
                diff_lines=8, estimated_cost_usd=0.001)
    base.update(kw)
    return AgentTrace(**base)


def test_trace_features_are_the_eight_axes() -> None:
    feats = trace_features(_trace(), AxisContext(solved=True, diff=None))
    assert len(feats) == 8 and all(isinstance(v, float) for v in feats.values())


def test_preferences_built_from_same_task_trajectories_train_a_model() -> None:
    # A clean, cheap, adherent winner vs a no-activation loser on the same task.
    winner = _trace(tool_calls=5, file_reads=2, commands=2, estimated_cost_usd=0.001)
    loser = _trace(tool_calls=0, file_reads=0, commands=0, status="failed",
                   changed_files=[], diff_lines=0, estimated_cost_usd=0.02)
    by_task = {"t1": [
        (winner, AxisContext(solved=True, diff=None)),
        (loser, AxisContext(solved=False, diff=None)),
    ]}
    prefs = preferences_from_same_task_trajectories(by_task)
    assert prefs, "expected at least one non-tie preference"
    # The model trained on trajectory-derived preferences ranks the winner higher.
    p = prefs[0]
    model = PreferenceModel()
    model.fit(prefs)
    assert model.prefers(p.winner_features, p.loser_features)
