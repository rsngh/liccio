"""Harness availability audit (Alpha 11/12 WS3)."""

from __future__ import annotations

from acp.evaluation.harness_availability import (
    audit_harness_availability,
    expected_harnesses,
)


def test_silently_absent_harness_degrades() -> None:
    # Both keys present, but only openai built -> claude is silently absent.
    env = {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}
    rep = audit_harness_availability({"openai_harness"}, env=env)
    assert rep.expected == ["claude_harness", "openai_harness"]
    assert rep.silently_absent == ["claude_harness"]
    assert rep.degraded


def test_all_expected_present_not_degraded() -> None:
    env = {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}
    rep = audit_harness_availability(
        {"openai_harness": True, "claude_harness": True}, env=env)
    assert not rep.degraded and not rep.silently_absent


def test_missing_key_is_not_expected() -> None:
    # No anthropic key -> claude not expected -> not degraded when absent.
    env = {"OPENAI_API_KEY": "x"}
    assert expected_harnesses(env) == ["openai_harness"]
    rep = audit_harness_availability({"openai_harness"}, env=env)
    assert not rep.degraded


def test_unhealthy_harness_counts_as_absent() -> None:
    env = {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}
    rep = audit_harness_availability(
        {"openai_harness": True, "claude_harness": False}, env=env)
    assert rep.silently_absent == ["claude_harness"] and rep.degraded
