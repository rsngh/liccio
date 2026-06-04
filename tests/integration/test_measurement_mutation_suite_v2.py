"""Measurement mutation suite v2 (Alpha 13 WS11).

Extends the v1 suite: every mutation must be caught by the measurement-QUALITY layer
(score + policy) and the provider-policy contract, not just classification — so a
contaminated or unsafe measurement can never pass the trust gate that promotes routing.
"""

from __future__ import annotations

from acp.evaluation.measurement_quality import measurement_quality_report
from acp.schemas.provider_policy import ProviderPolicy


def _cell(**kw):
    base = {"adapter": "openai_harness", "task_type": "bugfix", "success": True,
            "status": "succeeded", "tool_calls": 2, "is_harness": True,
            "commands": 1, "file_reads": 1, "cost_usd": 0.001}
    base.update(kw)
    return base


def test_mutation_enable_provider_retries_is_not_budget_safe() -> None:
    assert not ProviderPolicy(provider="openai", max_retries=2).is_budget_safe()
    assert ProviderPolicy(provider="openai", max_retries=0).is_budget_safe()


def test_mutation_hidden_harness_blocks_trust() -> None:
    rep = measurement_quality_report([_cell() for _ in range(5)], harness_available=False)
    assert not rep.trusted and rep.score.harness_available == 0.0


def test_mutation_secret_leak_blocks_trust() -> None:
    rep = measurement_quality_report([_cell() for _ in range(5)], secret_clean=False)
    assert not rep.trusted


def test_mutation_infra_burst_blocks_trust() -> None:
    cells = [_cell()] + [
        _cell(success=False, status="timed_out", timed_out=True, tool_calls=0,
              error="timed out") for _ in range(6)]
    rep = measurement_quality_report(cells)
    assert not rep.trusted and rep.score.infra_clean < 0.7


def test_mutation_disabled_tool_choice_lowers_activation_validity() -> None:
    # A run where harness attempts produced no tool calls -> activation invalid.
    cells = [_cell(success=False, status="failed", tool_calls=0, error="no edit")
             for _ in range(5)]
    rep = measurement_quality_report(cells)
    assert rep.score.tool_activation_validity == 0.0


def test_clean_run_passes_trust_gate() -> None:
    rep = measurement_quality_report([_cell() for _ in range(8)])
    assert rep.trusted and rep.score.overall >= 0.9
