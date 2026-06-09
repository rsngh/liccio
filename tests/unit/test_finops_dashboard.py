"""P5: user-facing FinOps dashboard / ledger."""

from __future__ import annotations

from acp.finops.dashboard import FinOpsLedger, SpendRecord


def _ledger() -> FinOpsLedger:
    led = FinOpsLedger()
    # calc family: cheap haiku single-shot solves it; expensive opus escalation also solves it
    led.add(SpendRecord(task_family="calc", provider="anthropic", model="haiku",
                        harness="single_shot", context_strategy="repo_map", topology="single",
                        policy="cheap_single", solved=True, executor_cost_usd=0.01,
                        verifier_cost_usd=0.002, session=0, memory_seeded=False))
    led.add(SpendRecord(task_family="calc", provider="anthropic", model="opus",
                        harness="single_shot", context_strategy="repo_map", topology="escalation",
                        policy="tier_escalation", solved=True, executor_cost_usd=0.20,
                        verifier_cost_usd=0.002, wasted_escalation_cost_usd=0.05,
                        thinking_cost_usd=0.03, session=0, memory_seeded=False))
    # context-gated family: only the context-router solves it; tier escalation wastes money, fails
    led.add(SpendRecord(task_family="ctx", provider="gemini", model="flash",
                        harness="harness", context_strategy="autonomous", topology="escalation",
                        policy="context_router", solved=True, executor_cost_usd=0.04,
                        verifier_cost_usd=0.002, session=1, memory_seeded=True))
    led.add(SpendRecord(task_family="ctx", provider="anthropic", model="opus",
                        harness="single_shot", context_strategy="minimal", topology="escalation",
                        policy="tier_escalation", solved=False, executor_cost_usd=0.25,
                        wasted_escalation_cost_usd=0.25, session=1, memory_seeded=False))
    return led


def test_cost_per_verified_success_by_model() -> None:
    by_model = _ledger().cost_per_verified_success_by("model")
    # haiku solved at $0.012 (0.01 exec + 0.002 verify); cheapest model per success
    assert by_model["haiku"] == 0.012
    # opus: two attempts, only the calc one solved -> (0.282 + 0.25) / 1 success
    assert by_model["opus"] == round((0.20 + 0.002 + 0.05 + 0.03) + (0.25 + 0.25), 6)


def test_unknown_dimension_rejected() -> None:
    import pytest
    with pytest.raises(ValueError):
        _ledger().cost_per_verified_success_by("not_a_dim")


def test_cost_buckets_sum() -> None:
    led = _ledger()
    assert led.verifier_cost() == round(0.002 * 3, 6)
    assert led.thinking_cost() == 0.03
    assert led.wasted_escalation_cost() == round(0.05 + 0.25, 6)


def test_recommended_policy_by_family_picks_cheapest_verified() -> None:
    rec = _ledger().recommended_policy_by_family()
    assert rec["calc"] == "cheap_single"        # cheaper than tier_escalation, both verified
    assert rec["ctx"] == "context_router"        # tier_escalation never verified here


def test_memory_savings_and_dashboard_shape() -> None:
    led = _ledger()
    mem = led.memory_savings_over_time()
    assert set(mem["per_session"]) == {0, 1}
    # a memory-seeded route exists and is cheaper than the failing memoryless ones
    assert mem["with_memory"] is not None
    d = led.dashboard()
    assert d["n_attempts"] == 4 and d["n_verified_success"] == 3
    assert "by_dimension" in d and "topology" in d["by_dimension"]
    text = led.render_text()
    assert "FinOps dashboard" in text and "recommend [calc]" in text
