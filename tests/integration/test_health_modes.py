"""Control-plane health modes (Alpha 11, WS4)."""

from __future__ import annotations

from acp.api.service import AppService
from acp.core.config import ACPSettings


def _svc(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'h.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_lab_mode_reports_status(tmp_path) -> None:
    h = _svc(tmp_path).control_plane_health(mode="lab")
    assert h["mode"] == "lab"
    assert "production_gates" in h
    assert "production_ready" in h


def test_production_mode_not_ready_on_empty_lab(tmp_path) -> None:
    # A fresh lab has no OPE log / docker-live report -> production not ready.
    h = _svc(tmp_path).control_plane_health(mode="production")
    assert h["production_ready"] is False
    assert h["failed_production_gates"]
    assert h["status"] == "degraded"


def test_production_gates_are_explicit(tmp_path) -> None:
    h = _svc(tmp_path).control_plane_health(mode="production")
    for gate in ("artifact_manifest_valid", "docker_live_security_passed",
                 "ope_overlap_sufficient", "test_reports_present"):
        assert gate in h["production_gates"]


def test_health_has_measurement_section(tmp_path) -> None:
    # WS5/WS9: measurement-trust signals are first-class in the health snapshot.
    h = _svc(tmp_path).control_plane_health(mode="lab")
    assert "measurement" in h
    m = h["measurement"]
    for k in ("solve_rate_conclusive", "infra_failure_rate", "contaminated",
              "harness_availability_degraded", "tool_activation_by_adapter"):
        assert k in m


def test_health_surfaces_harness_benefit_and_quality(tmp_path) -> None:
    # WS8: HAR/HFR/PWL per adapter + measurement-quality overall in the snapshot.
    m = _svc(tmp_path).control_plane_health(mode="lab")["measurement"]
    assert "harness_benefit_by_adapter" in m
    assert "measurement_quality_overall" in m


def test_health_has_skills_section(tmp_path) -> None:
    # Round 18: self-improving skills summary is part of the health snapshot.
    h = _svc(tmp_path).control_plane_health(mode="lab")
    assert "skills" in h
    for k in ("active_skills", "n_active_skills", "evolution_by_action", "recent_events"):
        assert k in h["skills"]


def test_production_gate_includes_vendor_harness(tmp_path) -> None:
    # Alpha 22 WS12: vendor-native harness pass is a production gate.
    h = _svc(tmp_path).control_plane_health(mode="production")
    assert "vendor_harness_live_passed" in h["production_gates"]


def test_health_has_benchmark_section_and_gate(tmp_path) -> None:
    # Alpha 23 WS7: graded benchmark capability is a first-class health section, and a
    # real difficulty-stratified baseline is a production gate.
    h = _svc(tmp_path).control_plane_health(mode="production")
    assert "benchmark" in h
    for key in ("baseline_overall", "baseline_by_difficulty", "discriminating",
                "skill_ab_decision"):
        assert key in h["benchmark"]
    assert "benchmark_baseline_present" in h["production_gates"]


def test_production_gates_are_explicit_and_fail_closed(tmp_path) -> None:
    # Alpha 25 (test H): production health must fail for EXPLICIT reasons only — every
    # critical gate is named, and an empty lab is not production-ready.
    h = _svc(tmp_path).control_plane_health(mode="production")
    required_gates = {
        "artifact_manifest_valid", "docker_live_security_passed", "ope_overlap_sufficient",
        "vendor_harness_live_passed", "measurement_quality_trusted",
        "benchmark_baseline_present", "report_truth_consistent",
    }
    assert required_gates <= set(h["production_gates"])
    # an empty lab is not production-ready, and every failure is a named gate
    assert not h["production_ready"]
    assert h["failed_production_gates"]
    assert all(g in h["production_gates"] for g in h["failed_production_gates"])


def test_report_truth_is_a_production_gate(tmp_path) -> None:
    # Alpha 25: stale CURRENT_STATUS counts must be able to fail production health.
    h = _svc(tmp_path).control_plane_health(mode="production")
    assert "report_truth_consistent" in h["production_gates"]
