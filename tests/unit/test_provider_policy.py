"""Provider call policy is declared and budget-safe (Alpha 11/12 WS2)."""

from __future__ import annotations

from acp.agents.claude_harness import ClaudeHarnessAdapter
from acp.agents.openai_harness import OpenAIHarnessAdapter
from acp.schemas.provider_policy import ProviderPolicy


def test_openai_policy_is_budget_safe() -> None:
    p = OpenAIHarnessAdapter().provider_policy()
    assert p.max_retries == 0 and p.per_call_timeout_s > 0
    assert p.retry_non_timeout_only and p.is_budget_safe()


def test_claude_policy_is_budget_safe() -> None:
    p = ClaudeHarnessAdapter().provider_policy()
    assert p.max_retries == 0 and p.is_budget_safe()


def test_policy_with_retries_is_not_budget_safe() -> None:
    assert not ProviderPolicy(provider="x", max_retries=2).is_budget_safe()
