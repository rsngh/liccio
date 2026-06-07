"""Concrete providers + registry (GOALS Alpha 43 P8).

Anthropic is live-capable here; OpenAI/Gemini/Codex/OpenHands are hooks that self-report
unavailable with a reason when their SDK/key/binary is missing. Detection is import/env/PATH
only — never a network call — so unit tests are hermetic.
"""

from __future__ import annotations

import os
import shutil

from acp.core.optional import try_import
from acp.providers.base import (
    Provider,
    ProviderAvailability,
    ProviderCapability,
    ProviderCostModel,
)

# published $/1M token prices (used only when the SDK/key are present; else cost is "unknown")
_COSTS = {
    "anthropic": ("claude-sonnet-4-6", 3.0, 15.0),
    "openai": ("gpt-4o", 2.5, 10.0),
    "gemini": ("gemini-2.5-pro", 1.25, 10.0),
}


class _SDKKeyProvider(Provider):
    sdk_module = ""
    env_key = ""

    def availability(self) -> ProviderAvailability:
        sdk = try_import(self.sdk_module) is not None if self.sdk_module else False
        key = bool(os.environ.get(self.env_key))
        if sdk and key:
            reason = "ok"
        elif not sdk and not key:
            reason = f"{self.sdk_module} SDK not installed and {self.env_key} not set"
        elif not sdk:
            reason = f"{self.sdk_module} SDK not installed"
        else:
            reason = f"{self.env_key} not set"
        return ProviderAvailability(self.name, sdk and key, reason, sdk_present=sdk,
                                    key_present=key)

    def cost_model(self, model: str = "") -> ProviderCostModel:
        if self.name in _COSTS:
            m, i, o = _COSTS[self.name]
            return ProviderCostModel(self.name, model or m, i, o, unknown_cost_behavior="estimate")
        return ProviderCostModel(self.name, model, None, None, unknown_cost_behavior="unknown")


class AnthropicProvider(_SDKKeyProvider):
    def __init__(self) -> None:
        super().__init__(name="anthropic",
                         capability=ProviderCapability(supports_tool_loop=True,
                                                       supports_json_tools=True,
                                                       supports_command_traces=True))
        self.sdk_module = "anthropic"
        self.env_key = "ACP_ANTHROPIC_API_KEY"


class OpenAIProvider(_SDKKeyProvider):
    def __init__(self) -> None:
        super().__init__(name="openai",
                         capability=ProviderCapability(supports_tool_loop=True,
                                                       supports_json_tools=True))
        self.sdk_module = "openai"
        self.env_key = "ACP_OPENAI_API_KEY"


class GeminiProvider(_SDKKeyProvider):
    def __init__(self) -> None:
        super().__init__(name="gemini",
                         capability=ProviderCapability(supports_tool_loop=True,
                                                       supports_json_tools=True))
        self.sdk_module = "google.generativeai"
        self.env_key = "ACP_GEMINI_API_KEY"


class _BinaryProvider(Provider):
    binary = ""

    def availability(self) -> ProviderAvailability:
        present = shutil.which(self.binary) is not None
        return ProviderAvailability(self.name, present,
                                    "ok" if present else f"{self.binary} not found on PATH",
                                    binary_present=present)


class CodexProvider(_BinaryProvider):
    def __init__(self) -> None:
        super().__init__(name="codex",
                         capability=ProviderCapability(supports_tool_loop=True,
                                                       supports_command_traces=True))
        self.binary = "codex"


class OpenHandsProvider(_SDKKeyProvider):
    def __init__(self) -> None:
        super().__init__(name="openhands",
                         capability=ProviderCapability(supports_tool_loop=True))
        self.sdk_module = "openhands"
        self.env_key = "OPENHANDS_SERVER_URL"


def all_providers() -> list[Provider]:
    return [AnthropicProvider(), OpenAIProvider(), GeminiProvider(), CodexProvider(),
            OpenHandsProvider()]


def provider_health() -> dict:
    """`acp provider health` payload: availability + capability + cost per provider."""
    rows = []
    for p in all_providers():
        av = p.availability()
        cm = p.cost_model()
        rows.append({
            "provider": p.name, **av.to_dict(),
            "capability": p.capability.__dict__,
            "cost_known": cm.is_known,
            "budget_policy": {"max_retries": p.budget.max_retries,
                              "per_call_timeout_s": p.budget.per_call_timeout_s},
        })
    return {"providers": rows,
            "available": [r["provider"] for r in rows if r["available"]],
            "unavailable": [r["provider"] for r in rows if not r["available"]]}
