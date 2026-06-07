"""Provider abstraction (GOALS Alpha 43 P8).

ACP routes ABOVE provider backends. A Provider declares its capabilities, availability (with an
actionable reason when down), a cost model (or explicit unknown), and a budget/retry policy. The
hard contract: an unavailable or failing provider yields an infra/inconclusive outcome — never a
capability failure — and never updates the capability matrix. OpenAI/Gemini are hooks here:
available only if their SDK+key exist; otherwise discoverable-and-down. No network in unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderCapability:
    supports_tool_loop: bool = False
    supports_readonly_advisor: bool = True
    supports_parallel_sampling: bool = True
    supports_json_tools: bool = False
    supports_command_traces: bool = False
    supports_token_usage: bool = True
    supports_cost_estimate: bool = True


@dataclass(frozen=True)
class ProviderAvailability:
    provider: str
    available: bool
    reason: str
    sdk_present: bool = False
    key_present: bool = False
    binary_present: bool | None = None
    network_reachable: bool | None = None        # optional; never probed in unit tests

    def to_dict(self) -> dict:
        return {"provider": self.provider, "available": self.available, "reason": self.reason,
                "sdk_present": self.sdk_present, "key_present": self.key_present,
                "binary_present": self.binary_present, "network_reachable": self.network_reachable}


@dataclass(frozen=True)
class ProviderCostModel:
    provider: str
    model: str
    input_cost_per_million: float | None
    output_cost_per_million: float | None
    tool_call_cost: float = 0.0
    unknown_cost_behavior: str = "estimate"      # estimate | unknown

    @property
    def is_known(self) -> bool:
        return self.input_cost_per_million is not None and self.output_cost_per_million is not None


@dataclass(frozen=True)
class ProviderBudgetPolicy:
    max_retries: int = 0                          # budget-safe default
    per_call_timeout_s: float = 60.0
    wall_clock_budget_s: float = 600.0


@dataclass
class Provider:
    """A normalized provider hook. Subclasses set how availability is detected."""

    name: str
    capability: ProviderCapability = field(default_factory=ProviderCapability)
    budget: ProviderBudgetPolicy = field(default_factory=ProviderBudgetPolicy)

    def availability(self) -> ProviderAvailability:        # overridden per provider
        raise NotImplementedError

    def cost_model(self, model: str = "") -> ProviderCostModel:
        return ProviderCostModel(self.name, model, None, None, unknown_cost_behavior="unknown")

    def classify_failure(self, *, available: bool) -> str:
        """A provider that is unavailable/failed yields an INFRA outcome, not a capability one."""
        return "task_failure" if available else "infra_provider_unavailable"
