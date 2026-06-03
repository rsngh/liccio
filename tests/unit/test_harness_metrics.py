"""Unit tests for harness activation / adherence metrics (alpha 11/12 WS6)."""

from __future__ import annotations

import json

from acp.evaluation.harness_metrics import (
    activation_report,
    adherence_report,
    default_harness_metrics_dataset,
    harness_benefit_metrics,
)
from acp.schemas.harness_metrics import HarnessBenefitMetrics
from acp.schemas.trace import AgentTrace


def _harness(**kw: object) -> AgentTrace:
    base: dict[str, object] = {
        "attempt_id": "t", "adapter_name": "h", "is_harness": True, "tool_calls": 3,
    }
    base.update(kw)
    return AgentTrace(**base)  # type: ignore[arg-type]


def test_activation_true_for_harness_with_tool_calls() -> None:
    rep = activation_report(_harness(tool_calls=4))
    assert rep.activated is True
    assert rep.activation_failure_reason is None
    assert rep.n_tool_calls == 4


def test_activation_false_when_not_a_harness() -> None:
    rep = activation_report(_harness(is_harness=False, tool_calls=5))
    assert rep.activated is False
    assert rep.activation_failure_reason == "not_a_harness"


def test_activation_false_when_no_tool_calls() -> None:
    rep = activation_report(_harness(tool_calls=0))
    assert rep.activated is False
    assert rep.activation_failure_reason == "no_tool_calls"


def test_adherence_followed_when_read_write_run_present() -> None:
    rep = adherence_report(
        _harness(file_reads=2, file_writes=["a.py"], commands=1, error=None)
    )
    assert rep.followed is True
    assert rep.phase_adherence == 1.0
    assert rep.adherence_decay == 0.0
    assert rep.adherence_failure_reason is None


def test_adherence_not_followed_without_changes() -> None:
    rep = adherence_report(_harness(file_reads=2, file_writes=[], commands=1))
    assert rep.followed is False
    assert rep.adherence_failure_reason == "no_changes"


def test_adherence_decay_flags_skipped_verification() -> None:
    # read + write done, but never ran/verified (and errored) -> decay > 0
    rep = adherence_report(
        _harness(file_reads=2, file_writes=["a.py"], commands=0, error="boom")
    )
    assert rep.followed is False
    assert rep.adherence_failure_reason == "no_verification"
    assert rep.adherence_decay == 1.0


def test_har_hfr_pwl_on_synthetic_dataset() -> None:
    data = default_harness_metrics_dataset()
    traces = [t for t, _ in data]
    solved = {t.attempt_id: s for t, s in data}
    m = harness_benefit_metrics(traces, solved)

    # 4 harness traces (a5 simple adapter excluded); 3 activated.
    assert m.sample_size == 4
    assert m.har == round(3 / 4, 4)
    # activated attempts: a1(solved), a2(unsolved), a4(solved) -> PWL 2/3.
    assert m.pwl == round(2 / 3, 4)
    # a2 activated-but-unsolved lowers PWL but not HAR.
    assert m.har > m.pwl


def test_unsolved_activated_lowers_pwl_not_har() -> None:
    data = default_harness_metrics_dataset()
    traces = [t for t, _ in data]
    # flip a2 to solved -> PWL becomes 1.0, HAR unchanged.
    solved = {t.attempt_id: s for t, s in data}
    solved["a2"] = True
    m = harness_benefit_metrics(traces, solved)
    assert m.pwl == 1.0
    assert m.har == round(3 / 4, 4)


def test_by_task_type_and_by_model_populated() -> None:
    data = default_harness_metrics_dataset()
    traces = [t for t, _ in data]
    solved = {t.attempt_id: s for t, s in data}
    m = harness_benefit_metrics(traces, solved)

    assert set(m.by_task_type) == {"bugfix", "feature"}
    assert set(m.by_model) == {"claude-sonnet", "gpt-x"}
    # bugfix harness attempts: a1(act,solved), a2(act,unsolved) -> HAR 1.0, PWL .5
    assert m.by_task_type["bugfix"]["har"] == 1.0
    assert m.by_task_type["bugfix"]["pwl"] == 0.5
    # feature: a3(not activated), a4(act,solved) -> HAR .5, PWL 1.0
    assert m.by_task_type["feature"]["har"] == 0.5
    assert m.by_task_type["feature"]["pwl"] == 1.0


def test_json_serializable() -> None:
    data = default_harness_metrics_dataset()
    traces = [t for t, _ in data]
    solved = {t.attempt_id: s for t, s in data}
    m = harness_benefit_metrics(traces, solved)
    blob = m.canonical_json()
    round_tripped = HarnessBenefitMetrics.model_validate(json.loads(blob))
    assert round_tripped == m
