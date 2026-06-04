"""Measurement-quality scoring + policy (Alpha 13 WS3)."""

from __future__ import annotations

from acp.evaluation.measurement_quality import (
    measurement_quality_report,
    score_measurement_quality,
)
from acp.schemas.measurement_quality import MeasurementQualityPolicy


def _cell(**kw):
    base = {"adapter": "openai_harness", "task_type": "bugfix", "success": True,
            "status": "succeeded", "tool_calls": 2, "is_harness": True,
            "commands": 1, "file_reads": 1, "cost_usd": 0.001}
    base.update(kw)
    return base


def test_clean_batch_scores_high_and_is_trusted() -> None:
    score = score_measurement_quality([_cell() for _ in range(5)])
    assert score.overall == 1.0 and score.infra_clean == 1.0
    rep = measurement_quality_report([_cell() for _ in range(5)])
    assert rep.trusted and not rep.block_reasons


def test_infra_heavy_batch_lowers_infra_clean_and_blocks() -> None:
    cells = [_cell()] + [
        _cell(success=False, status="timed_out", timed_out=True, tool_calls=0,
              error="timed out") for _ in range(4)]
    score = score_measurement_quality(cells)
    assert score.infra_clean < 0.7
    rep = measurement_quality_report(cells)
    assert not rep.trusted and any("infra_clean" in r for r in rep.block_reasons)


def test_silently_absent_harness_blocks() -> None:
    rep = measurement_quality_report([_cell() for _ in range(5)], harness_available=False)
    assert not rep.trusted and any("silently absent" in r for r in rep.block_reasons)


def test_secret_leak_blocks_under_default_policy() -> None:
    rep = measurement_quality_report([_cell() for _ in range(5)], secret_clean=False)
    assert not rep.trusted


def test_policy_threshold_is_configurable() -> None:
    score = score_measurement_quality([_cell() for _ in range(5)])
    strict = MeasurementQualityPolicy(min_overall=1.01)
    trusted, reasons = strict.evaluate(score)
    assert not trusted and reasons
