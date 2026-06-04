"""Provider policy registry + violation detection (Alpha 14 WS6)."""

from __future__ import annotations

import pytest

from acp.agents.provider_registry import ProviderPolicyRegistry
from acp.schemas.provider_policy import (
    ProviderCallRecord,
    ProviderPolicy,
    detect_violations,
)


def test_registry_defaults_are_budget_safe() -> None:
    reg = ProviderPolicyRegistry()
    assert reg.all_budget_safe()
    assert reg.get("openai").max_retries == 0
    assert reg.get("unknown_provider").is_budget_safe()  # safe default


def test_registry_refuses_unsafe_policy() -> None:
    reg = ProviderPolicyRegistry()
    with pytest.raises(ValueError):
        reg.register(ProviderPolicy(provider="openai", max_retries=3))


def test_detect_retry_violation() -> None:
    pol = ProviderPolicy(provider="openai", max_retries=0, per_call_timeout_s=60)
    rec = ProviderCallRecord(provider="openai", retries_used=2, wall_time_s=5.0)
    viols = detect_violations(rec, pol)
    assert any(v.kind == "retry_violation" for v in viols)


def test_detect_timeout_violation() -> None:
    pol = ProviderPolicy(provider="openai", max_retries=0, per_call_timeout_s=60)
    rec = ProviderCallRecord(provider="openai", retries_used=0, wall_time_s=241.0)
    viols = detect_violations(rec, pol, wall_budget_s=120.0)
    assert any(v.kind == "timeout_violation" for v in viols)


def test_compliant_call_has_no_violations() -> None:
    pol = ProviderPolicy(provider="openai", max_retries=0, per_call_timeout_s=60)
    rec = ProviderCallRecord(provider="openai", retries_used=0, wall_time_s=8.0)
    assert detect_violations(rec, pol) == []
