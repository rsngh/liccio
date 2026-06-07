# ruff: noqa: E501
"""Governed vendor-CLI adapter — offline tests (no network): availability gating + scrubbing."""

from __future__ import annotations

from acp.agents.claude_agent import ClaudeAgentAdapter
from acp.agents.gemini_agent import GeminiAgentAdapter
from acp.agents.sandbox_cli import (
    VENDOR_BACKING,
    _scrub,
    _secret_leak,
    all_vendor_status,
    vendor_status,
)


def test_all_four_vendors_registered() -> None:
    assert set(VENDOR_BACKING) == {"gemini_cli", "openhands", "codex_cli", "claude_code"}
    st = all_vendor_status()
    assert set(st) == set(VENDOR_BACKING)
    for s in st.values():
        assert isinstance(s.available, bool) and isinstance(s.reason, str) and s.reason


def test_codex_unavailable_when_binary_absent() -> None:
    # codex CLI is not installed in CI -> availability-gated, reported with a reason (not faked)
    s = vendor_status("codex_cli")
    if not s.available:
        assert "codex" in s.reason.lower() or "openai" in s.reason.lower() or "sandbox" in s.reason.lower()


def test_unknown_vendor_is_unavailable() -> None:
    s = vendor_status("does_not_exist")
    assert not s.available


def test_secret_scrubbing(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSECRETKEYVALUE1234567")
    assert _secret_leak("leaked AIzaSECRETKEYVALUE1234567 here")
    assert "AIzaSECRETKEYVALUE1234567" not in _scrub("x AIzaSECRETKEYVALUE1234567 y")
    assert "<REDACTED>" in _scrub("x AIzaSECRETKEYVALUE1234567 y")


def test_thinking_budget_params_stored() -> None:
    assert ClaudeAgentAdapter(model="claude-sonnet-4-6", thinking_budget=2048).thinking_budget == 2048
    assert ClaudeAgentAdapter().thinking_budget == 0           # off by default
    assert GeminiAgentAdapter(model="gemini-2.5-flash", thinking_budget=1024).thinking_budget == 1024
    assert GeminiAgentAdapter().thinking_budget is None        # model default by default
