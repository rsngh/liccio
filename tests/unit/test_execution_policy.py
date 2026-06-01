"""Docker-required-for-harness governance (round-3 R3-3)."""

from __future__ import annotations

import pytest

from acp.core.errors import PolicyViolation
from acp.core.policies import PolicyEngine


def test_required_backend_by_adapter_class() -> None:
    eng = PolicyEngine()
    assert eng.required_backend(is_harness=True, is_model_adapter=False) == "docker_required"
    assert eng.required_backend(is_harness=False, is_model_adapter=True) == "docker_preferred"
    assert eng.required_backend(is_harness=False, is_model_adapter=False) == "local_allowed"


def test_harness_local_blocked_without_override() -> None:
    eng = PolicyEngine()
    with pytest.raises(PolicyViolation):
        eng.check_execution_backend(is_harness=True, is_model_adapter=False, backend="local")


def test_harness_local_allowed_with_override_audited() -> None:
    eng = PolicyEngine()
    decision = eng.check_execution_backend(
        is_harness=True, is_model_adapter=False, backend="local", allow_local_harness=True,
    )
    assert decision == "local_override"
    assert any(e.event_type == "local_harness_override" for e in eng.audit.events)


def test_harness_docker_ok() -> None:
    eng = PolicyEngine()
    assert eng.check_execution_backend(
        is_harness=True, is_model_adapter=False, backend="docker"
    ) == "docker_required"


def test_model_adapter_local_is_audited_not_blocked() -> None:
    eng = PolicyEngine()
    eng.check_execution_backend(is_harness=False, is_model_adapter=True, backend="local")
    assert any(e.event_type == "model_adapter_local" for e in eng.audit.events)


def test_fake_patch_local_allowed() -> None:
    eng = PolicyEngine()
    assert eng.check_execution_backend(
        is_harness=False, is_model_adapter=False, backend="local"
    ) == "local_allowed"
