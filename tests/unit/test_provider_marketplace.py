"""Provider marketplace scorecard tests (GOALS Alpha 44 P10)."""

from __future__ import annotations

from acp.providers.marketplace import ProviderMarketplace


def test_scorecard_separates_evidence_classes() -> None:
    m = ProviderMarketplace(min_cells=30)
    m.classify(provider="anthropic", available=True, contract_passed=True, conclusive_cells=318,
               verified=0.9, cost=0.0015)
    m.classify(provider="openai", available=False, contract_passed=True, reason="key missing")
    m.classify(provider="gemini", available=False, contract_passed=True, reason="sdk missing")
    m.classify(provider="legacy", available=False, contract_passed=True, has_replay=True)
    sc = m.scorecard()["by_evidence_class"]
    assert sc["live_conclusive"] == ["anthropic"]
    assert set(sc["mock_contract_only"]) == {"openai", "gemini"}
    assert sc["replay_imported"] == ["legacy"]


def test_mix_recommends_only_feasible() -> None:
    m = ProviderMarketplace(min_cells=30)
    m.classify(provider="anthropic", available=True, contract_passed=True, conclusive_cells=318,
               verified=0.9, cost=0.0015)
    m.classify(provider="openai", available=False, contract_passed=True, reason="unavailable")
    rec = m.mix_recommendation()
    assert rec["recommended_primary"] == "anthropic"
    assert rec["feasible_providers"] == ["anthropic"]
    assert "openai" in rec["not_ranked"]


def test_available_but_too_few_cells_not_live_conclusive() -> None:
    m = ProviderMarketplace(min_cells=30)
    r = m.classify(provider="anthropic", available=True, contract_passed=True, conclusive_cells=5)
    assert r.evidence_class != "live_conclusive"
    assert m.mix_recommendation()["recommended_primary"] is None
