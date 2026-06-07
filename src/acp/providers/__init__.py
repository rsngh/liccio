"""Provider abstraction (GOALS Alpha 43 P8): normalized capability/availability/cost/budget
across Anthropic (live here) + OpenAI/Gemini/Codex/OpenHands hooks (self-skipping)."""

from acp.providers.base import (
    Provider,
    ProviderAvailability,
    ProviderCapability,
    ProviderCostModel,
)
from acp.providers.contracts import check_provider_contract, provider_contract_gate
from acp.providers.registry import all_providers, provider_health

__all__ = ["Provider", "ProviderAvailability", "ProviderCapability", "ProviderCostModel",
           "check_provider_contract", "provider_contract_gate", "all_providers",
           "provider_health"]
