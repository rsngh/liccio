"""Capability registry for agent adapters (alpha-6 WS1).

Introspects an :class:`AgentRegistry` and classifies every adapter into one of
the status-schema categories (``docs/status_schema.md``):

* ``deterministic`` — fake / patch adapters with no external dependency.
* ``simple_model`` — single-shot JSON-edit LLM adapters (``is_harness=False``).
* ``acp_harness`` — ACP true tool-loop harnesses (``is_harness=True``, no
  ``category == "vendor"``).
* ``vendor`` — wrappers around external vendor coding agents
  (:class:`~acp.agents.vendor_base.VendorHarnessAdapter`, ``category="vendor"``).

For each adapter it reports the category, the requirement (SDK module / CLI
binary / API key, when known) and live availability via the adapter's own
``healthcheck`` — so a caller can see, for the current environment, exactly
which agents are real, which are degraded, and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.agents.base import AgentAdapter
from acp.agents.registry import AgentRegistry
from acp.core.enums import AgentKind

_DETERMINISTIC_KINDS = {AgentKind.FAKE, AgentKind.PATCH}


@dataclass(frozen=True)
class AdapterCapability:
    """A single adapter's classification + live availability."""

    name: str
    category: str  # deterministic | simple_model | acp_harness | vendor
    kind: str
    is_harness: bool
    requirement: str | None
    available: bool
    detail: str


@dataclass
class CapabilityRegistry:
    """Snapshot of every adapter's category + availability."""

    entries: list[AdapterCapability] = field(default_factory=list)

    def by_category(self, category: str) -> list[AdapterCapability]:
        return [e for e in self.entries if e.category == category]

    def get(self, name: str) -> AdapterCapability:
        for e in self.entries:
            if e.name == name:
                return e
        raise KeyError(f"no capability entry for {name!r}")

    def names(self) -> list[str]:
        return sorted(e.name for e in self.entries)


def classify(adapter: AgentAdapter) -> str:
    """Return the status-schema category for an adapter."""
    if getattr(adapter, "category", None) == "vendor":
        return "vendor"
    if getattr(adapter, "is_harness", False):
        return "acp_harness"
    if getattr(adapter, "kind", None) in _DETERMINISTIC_KINDS:
        return "deterministic"
    return "simple_model"


def _requirement_of(adapter: AgentAdapter) -> str | None:
    cap = getattr(adapter, "capability", None)
    if cap is None:
        return None
    suffix = " (+key)" if getattr(cap, "requires_key", False) else ""
    return f"{cap.kind}:{cap.requirement}{suffix}"


async def build_capability_registry(registry: AgentRegistry) -> CapabilityRegistry:
    """Introspect ``registry`` and report category + live availability per adapter."""
    health = await registry.healthcheck_all()
    entries: list[AdapterCapability] = []
    for name in registry.names():
        adapter = registry.get(name)
        h = health.get(name)
        entries.append(AdapterCapability(
            name=name,
            category=classify(adapter),
            kind=str(getattr(adapter.kind, "value", adapter.kind)),
            is_harness=bool(getattr(adapter, "is_harness", False)),
            requirement=_requirement_of(adapter),
            available=bool(h.available) if h is not None else False,
            detail=h.detail if h is not None else "no healthcheck",
        ))
    return CapabilityRegistry(entries=entries)
