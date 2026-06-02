"""Integration tests for the capability matrix population campaign (Alpha 8 WS13)."""

from __future__ import annotations

import json

from acp.evaluation.capability_campaign import (
    campaign_summary,
    generate_campaign_report,
)


def test_campaign_yields_at_least_30_sufficient_cells() -> None:
    matrix = generate_campaign_report()
    summary = campaign_summary(matrix)
    assert summary["n_sufficient"] >= 30
    assert summary["n_cells"] >= summary["n_sufficient"]
    # the default campaign intentionally leaves some cells under-sampled so the
    # exploration plan has something to explain.
    assert summary["n_under_sampled"] > 0


def test_under_sampled_cells_carry_low_sample_flag() -> None:
    # A single repetition forces every cell below MIN_SAMPLE.
    matrix = generate_campaign_report(repetitions=1)
    under = [c for c in matrix.cells() if not c.sufficient_data]
    assert under, "expected under-sampled cells with reps=1"
    for cell in under:
        assert "low_sample" in cell.flags


def test_summary_is_json_serializable_and_reports_sufficiency() -> None:
    matrix = generate_campaign_report()
    summary = campaign_summary(matrix)
    blob = json.dumps(summary)  # must not raise
    assert json.loads(blob)["n_sufficient"] >= 30
    assert "per_task_type" in summary
    assert summary["per_task_type"]


def test_exploration_plan_names_missing_sample_cells() -> None:
    # reps=2 < MIN_SAMPLE(5) so all cells are under-sampled and named.
    matrix = generate_campaign_report(repetitions=2)
    summary = campaign_summary(matrix)
    plan = summary["exploration_plan"]
    assert plan["n_targets"] == summary["n_under_sampled"]
    assert plan["n_targets"] == summary["n_cells"]
    assert plan["targets"]
    for target in plan["targets"]:
        assert target["samples_needed"] > 0
        assert target["task_type"]


def test_exploration_plan_empty_when_all_sufficient() -> None:
    # reps=15 lifts even the sparse (1/3) buckets above MIN_SAMPLE(5).
    matrix = generate_campaign_report(repetitions=15)
    summary = campaign_summary(matrix)
    assert summary["n_under_sampled"] == 0
    assert summary["exploration_plan"]["n_targets"] == 0
