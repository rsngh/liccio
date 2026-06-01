"""Agent registry (charter §12.7)."""

from __future__ import annotations

from acp.agents.base import AgentAdapter
from acp.schemas.agent import AgentHealth


class AgentRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, AgentAdapter] = {}

    def register(self, adapter: AgentAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> AgentAdapter:
        if name not in self._adapters:
            raise KeyError(f"no agent adapter named {name!r}")
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(self._adapters)

    async def available(self) -> list[str]:
        out = []
        for name, adapter in self._adapters.items():
            try:
                health = await adapter.healthcheck()
                if health.available:
                    out.append(name)
            except Exception:  # noqa: BLE001 - unavailable adapter must not crash
                continue
        return sorted(out)

    async def healthcheck_all(self) -> dict[str, AgentHealth]:
        result: dict[str, AgentHealth] = {}
        for name, adapter in self._adapters.items():
            try:
                result[name] = await adapter.healthcheck()
            except Exception as exc:  # noqa: BLE001
                result[name] = AgentHealth(
                    name=name, kind=adapter.kind, available=False, detail=str(exc)
                )
        return result
