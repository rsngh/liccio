"""Context-strategy DOWNSTREAM benchmark tests (Alpha 7, WS7).

Unlike the recall-only Alpha 6 sweep, this benchmark runs each fixture task
end-to-end under each pinned strategy and scores by DOWNSTREAM task success.
These tests assert one result per (task, strategy, rep) carrying a run status +
recall + cost + latency, that a best strategy is chosen by downstream success,
and that the report dict is JSON-serializable — all quickly.
"""

from __future__ import annotations

import json

import pytest

from acp.evaluation.context_downstream_benchmark import (
    _calc_task,
    report_to_markdown,
    run_context_downstream_benchmark,
)

_STRATEGIES = ("hybrid_keyword_embedding", "minimal")
_REPS = 2
_TASKS = [_calc_task()]


@pytest.fixture(scope="module")
def report():
    # Compute the sweep once (it runs real agents) and share across assertions.
    return run_context_downstream_benchmark(
        tasks=_TASKS, strategies=_STRATEGIES, repetitions=_REPS
    )


def test_one_result_per_task_strategy_rep(report) -> None:
    tasks = [t.name for t in _TASKS]
    expected = len(tasks) * len(_STRATEGIES) * _REPS
    assert len(report.results) == expected
    # exactly one result per (task, strategy, rep) cell
    for task in tasks:
        for strat in _STRATEGIES:
            for rep in range(_REPS):
                assert report.result_for(task, strat, rep) is not None


def test_each_result_has_downstream_signals(report) -> None:
    for r in report.results:
        # downstream run actually executed and reached a terminal state
        assert r.run_status in {"succeeded", "failed"}
        # recall + cost + latency recorded for every cell
        assert 0.0 <= r.gold_recall <= 1.0
        assert r.cost_usd >= 0.0
        assert r.latency_s >= 0.0


def test_best_strategy_chosen_by_downstream_success(report) -> None:
    assert report.best_strategy in _STRATEGIES
    # at least one run solved its task end-to-end (deterministic patch fix)
    assert any(r.success for r in report.results)
    # the chosen winner has the top downstream success_rate among aggregates
    agg = {a["strategy"]: a for a in report.aggregates}
    best = agg[report.best_strategy]
    assert all(best["success_rate"] >= a["success_rate"] for a in report.aggregates)


def test_report_is_json_serializable_and_renders(report) -> None:
    payload = report.to_dict()
    text = json.dumps(payload)
    assert "best_strategy" in json.loads(text)
    md = report_to_markdown(report)
    assert "DOWNSTREAM" in md
