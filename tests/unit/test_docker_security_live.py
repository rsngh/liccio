"""Docker live security release gate (alpha-8 WS14).

Without Docker the live check reports an explicit skip and the gate refuses
production; the gate's pass/fail logic is exercised independently of Docker.
The live-pass assertions run only when Docker is actually available.
"""

from __future__ import annotations

import json

import pytest

from acp.evaluation.docker_security_live import (
    CHECK_NAMES,
    DockerSecurityGate,
    load_report,
    run_docker_security_live,
)
from acp.workspaces.docker import docker_available


def test_run_reports_skipped_without_docker() -> None:
    report = run_docker_security_live()
    if docker_available():
        pytest.skip("docker available; covered by live test")
    assert report["available"] is False
    assert report["skipped"] is True
    assert report["passed"] is False
    assert report["reason"] == "docker unavailable"
    names = [c["name"] for c in report["checks"]]
    assert names == CHECK_NAMES
    assert all(c["status"] == "skipped" for c in report["checks"])


def test_gate_refuses_when_no_report() -> None:
    allowed, reason = DockerSecurityGate.production_allowed(None)
    assert allowed is False
    assert reason


def test_gate_allows_passing_report() -> None:
    allowed, reason = DockerSecurityGate.production_allowed({"passed": True})
    assert allowed is True
    assert reason


def test_gate_refuses_failing_report() -> None:
    allowed, _ = DockerSecurityGate.production_allowed({"passed": False})
    assert allowed is False


def test_gate_refuses_skipped_report() -> None:
    allowed, _ = DockerSecurityGate.production_allowed(
        {"skipped": True, "passed": False})
    assert allowed is False


def test_gate_refuses_skipped_report_from_runner() -> None:
    # The skipped report (docker unavailable) must never satisfy the gate.
    allowed, _ = DockerSecurityGate.production_allowed(run_docker_security_live())
    if docker_available():
        pytest.skip("docker available; report may pass")
    assert allowed is False


def test_load_report_missing_and_roundtrip(tmp_path) -> None:
    assert load_report(tmp_path / "nope.json") is None
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"passed": True, "checks": []}))
    loaded = load_report(p)
    assert loaded is not None and loaded["passed"] is True


def test_load_report_invalid_json(tmp_path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json {")
    assert load_report(p) is None


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_live_checks_pass() -> None:
    report = run_docker_security_live()
    assert report["available"] is True
    failing = [c["name"] for c in report["checks"] if c["status"] != "pass"]
    assert not failing, f"failing checks: {failing}"
    allowed, _ = DockerSecurityGate.production_allowed(report)
    assert allowed is True
