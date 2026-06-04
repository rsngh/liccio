"""Provider policy registry (Alpha 14 WS6).

A single place that owns the budget-safety contract per provider, so every harness
resolves its policy from one source and SDK behavior that would exceed ACP budgets is
detectable. Defaults are budget-safe (max_retries=0 + per-call timeout); a caller can
register a stricter policy but the registry refuses an unsafe default.
"""

from __future__ import annotations

from acp.schemas.provider_policy import ProviderPolicy

# Budget-safe defaults per known provider.
_DEFAULTS: dict[str, ProviderPolicy] = {
    "openai": ProviderPolicy(provider="openai", max_retries=0, per_call_timeout_s=60.0),
    "anthropic": ProviderPolicy(provider="anthropic", max_retries=0,
                                per_call_timeout_s=60.0),
}


class ProviderPolicyRegistry:
    """Maps a provider name to its (budget-safe) ProviderPolicy."""

    def __init__(self) -> None:
        self._policies: dict[str, ProviderPolicy] = dict(_DEFAULTS)

    def get(self, provider: str) -> ProviderPolicy:
        """Resolve a provider's policy, defaulting to a budget-safe one."""
        return self._policies.get(
            provider, ProviderPolicy(provider=provider, max_retries=0,
                                     per_call_timeout_s=60.0))

    def register(self, policy: ProviderPolicy) -> None:
        """Register a policy. Refuses an unsafe one (would silently exceed budget)."""
        if not policy.is_budget_safe():
            raise ValueError(
                f"refusing unsafe provider policy for {policy.provider}: "
                "max_retries must be 0 and per_call_timeout_s > 0")
        self._policies[policy.provider] = policy

    def all_budget_safe(self) -> bool:
        return all(p.is_budget_safe() for p in self._policies.values())


_REGISTRY = ProviderPolicyRegistry()


def default_registry() -> ProviderPolicyRegistry:
    """The process-wide provider policy registry."""
    return _REGISTRY
