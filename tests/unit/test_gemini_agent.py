"""Gemini adapter — offline contract tests (no network).

Guards the availability/parse contract: unavailable without a key (never raises at import),
JSON extraction tolerates ```json fences and surrounding prose, and the kind/tiers wiring is sound.
The live solve-rate is measured in reports/hetero_arena_xprovider.json.
"""

from __future__ import annotations

import asyncio

from acp.agents.gemini_agent import GeminiAgentAdapter, _extract_json
from acp.core.enums import AgentKind


def test_kind_and_model_defaults() -> None:
    a = GeminiAgentAdapter()
    assert a.kind == AgentKind.GEMINI
    assert a.model_name == "gemini-2.5-flash"
    assert a.is_harness is False


def test_unavailable_without_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ACP_GEMINI_API_KEY", raising=False)
    health = asyncio.run(GeminiAgentAdapter().healthcheck())
    assert health.available is False
    assert "GEMINI_API_KEY" in health.detail


def test_extract_json_tolerates_fences_and_prose() -> None:
    assert _extract_json('```json\n{"files": {"r.py": "x"}}\n```') == '{"files": {"r.py": "x"}}'
    assert _extract_json('here you go: {"a": 1} done') == '{"a": 1}'
    assert _extract_json("no json here") == "{}"


def test_tiers_expose_gemini_provider() -> None:
    from evals.hetero_arena.tiers import ALL_TIERS, GEMINI_FLASH, GEMINI_PRO
    assert GEMINI_FLASH.provider == "gemini"
    assert GEMINI_PRO.provider == "gemini"
    # flash is genuinely cheaper than the cheapest Anthropic tier (haiku) on output
    assert GEMINI_FLASH.out_per_tok < ALL_TIERS["haiku"].out_per_tok
    # adapter factory routes provider correctly without network
    assert GEMINI_FLASH.adapter().kind == AgentKind.GEMINI
