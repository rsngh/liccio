"""Topology-action safety gate (Alpha 11/12 WS14)."""

from __future__ import annotations

from acp.routing.topology_safety import filter_topology, is_skip_allowed


def test_security_never_skips_strict_verification() -> None:
    ok, reason = is_skip_allowed("skip_strict_verification", "security_fix", "high")
    assert not ok and "forbidden" in reason


def test_high_risk_never_skips_reviewer() -> None:
    ok, _ = is_skip_allowed("skip_reviewer", "bugfix", "critical")
    assert not ok


def test_docs_lint_low_risk_can_skip_retrieval_to_save_cost() -> None:
    # Cheap cost-saving skips are allowed on low-risk, non-security tasks.
    allowed, rejected = filter_topology(
        ["skip_retrieval", "skip_planner"], "docs", "low")
    assert allowed == ["skip_retrieval", "skip_planner"] and not rejected


def test_filter_drops_only_unsafe_skips_and_explains() -> None:
    allowed, rejected = filter_topology(
        ["skip_retrieval", "skip_strict_verification"], "security_fix", "high")
    assert allowed == ["skip_retrieval"]            # cheap skip kept
    assert "skip_strict_verification" in rejected   # safety skip dropped + explained


def test_light_verifier_blocked_on_security() -> None:
    ok, _ = is_skip_allowed("run_light_verifier", "security_fix", "medium")
    assert not ok
