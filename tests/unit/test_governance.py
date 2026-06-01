"""Governance + observability tests (charter §22, §23)."""

from __future__ import annotations

import pytest

from acp.core.enums import RiskLevel
from acp.core.errors import PolicyViolation
from acp.core.policies import PolicyEngine
from acp.observability.exporters import JSONLExporter
from acp.observability.tracing import Tracer


def test_high_risk_cannot_auto_finalize() -> None:
    eng = PolicyEngine()
    with pytest.raises(PolicyViolation):
        eng.check_auto_finalize(RiskLevel.HIGH, experimental=False)
    with pytest.raises(PolicyViolation):
        eng.check_auto_finalize(RiskLevel.CRITICAL, experimental=False)


def test_low_risk_can_auto_finalize() -> None:
    PolicyEngine().check_auto_finalize(RiskLevel.LOW, experimental=False)


def test_experimental_cannot_auto_approve() -> None:
    with pytest.raises(PolicyViolation):
        PolicyEngine().check_auto_finalize(RiskLevel.LOW, experimental=True)


def test_network_denied_by_default() -> None:
    assert PolicyEngine().network_allowed() is False


def test_no_auto_merge_default() -> None:
    assert PolicyEngine().can_auto_merge() is False


def test_budget_exceeded_raises() -> None:
    with pytest.raises(PolicyViolation):
        PolicyEngine().check_budget(100.0)


def test_override_creates_audit_event() -> None:
    eng = PolicyEngine()
    eng.override("auto_merge", actor="alice", reason="hotfix")
    assert any(e.event_type == "policy_override" for e in eng.audit.events)


def test_trace_has_id_and_no_secrets(tmp_path) -> None:
    tracer = Tracer()
    trace_id = "trace_xyz"
    with tracer.span("acp.command.run", trace_id, exit_code=0,
                     env={"OPENAI_API_KEY": "sk-secret-123456"}):
        pass
    span = tracer.spans[0]
    assert span.trace_id == trace_id
    assert span.attributes["exit_code"] == 0
    # secret redacted in span attributes
    assert span.attributes["env"]["OPENAI_API_KEY"] == "***REDACTED***"

    exporter = JSONLExporter(tmp_path / "spans.jsonl")
    n = exporter.export(tracer.spans)
    assert n == 1
    records = exporter.read_all()
    assert records[0]["trace_id"] == trace_id
    assert "sk-secret-123456" not in records[0]["attributes"]["env"]["OPENAI_API_KEY"]


def test_command_span_includes_exit_code() -> None:
    tracer = Tracer()
    with tracer.span("acp.command.run", "t", exit_code=1):
        pass
    assert tracer.spans[0].attributes["exit_code"] == 1
