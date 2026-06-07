"""Provider contract tests (GOALS Alpha 43 P8) — no network; OpenAI/Gemini mocked via env."""

from __future__ import annotations

from acp.providers import (
    all_providers,
    check_provider_contract,
    provider_contract_gate,
    provider_health,
)
from acp.providers.registry import (
    AnthropicProvider,
    GeminiProvider,
    OpenAIProvider,
)


def test_all_providers_satisfy_contract() -> None:
    gate = provider_contract_gate(all_providers())
    assert gate["all_contracts_pass"], gate
    assert gate["n_providers"] >= 5


def test_unavailable_provider_has_actionable_reason(monkeypatch) -> None:
    monkeypatch.delenv("ACP_OPENAI_API_KEY", raising=False)
    av = OpenAIProvider().availability()
    assert not av.available
    assert "key" in av.reason.lower() or "sdk" in av.reason.lower()


def test_unavailable_is_infra_not_capability() -> None:
    # an unavailable provider failure must be infra/inconclusive, never a capability failure
    assert OpenAIProvider().classify_failure(available=False).startswith("infra")
    assert GeminiProvider().classify_failure(available=False).startswith("infra")


def test_openai_gemini_are_hooks_not_live_here(monkeypatch) -> None:
    monkeypatch.delenv("ACP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ACP_GEMINI_API_KEY", raising=False)
    health = provider_health()
    assert "openai" in health["unavailable"]
    assert "gemini" in health["unavailable"]
    # but they remain discoverable in the provider list with a reason
    names = {r["provider"] for r in health["providers"]}
    assert {"openai", "gemini", "anthropic"} <= names


def test_mocked_available_provider_passes_contract(monkeypatch) -> None:
    # simulate OpenAI being available WITHOUT any network call (env + SDK presence shim)
    monkeypatch.setenv("ACP_OPENAI_API_KEY", "sk-test")
    import acp.providers.registry as reg
    monkeypatch.setattr(reg, "try_import", lambda m: object())  # pretend the SDK is importable
    av = OpenAIProvider().availability()
    assert av.available and av.key_present and av.sdk_present
    assert check_provider_contract(OpenAIProvider())["contract_passed"]


def test_cost_model_present_or_unknown() -> None:
    cm = AnthropicProvider().cost_model()
    assert cm.is_known                       # anthropic has a published cost model
    assert OpenAIProvider().cost_model("gpt-4o").is_known
