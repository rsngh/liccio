"""Vendor-native harness module: health, fixture, classification (Alpha 22 WS5-9)."""

from __future__ import annotations

import subprocess

from acp.agents.vendor_native import (
    VENDOR_SPECS,
    VendorNativeHarness,
    VendorRunResult,
    _classify_vendor,
    build_smoke_fixture,
    detect_vendor_health,
    openhands_capability_level,
)


def test_health_detector_shape() -> None:
    h = detect_vendor_health()
    assert set(h) == {"codex_cli", "claude_code", "openhands"}
    for v in h.values():
        assert "available" in v
        if v["available"]:
            assert v.get("version")


def test_smoke_fixture_starts_failing(tmp_path) -> None:
    # WS6: the fixture is a REAL repo whose test fails until the bug is fixed.
    repo = build_smoke_fixture(tmp_path)
    assert (repo / "calculator.py").exists()
    pt = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo,
                        capture_output=True, text=True, check=False)
    assert pt.returncode != 0  # divide bug -> test_divide fails initially
    # ... and a correct fix makes it pass (proves the fixture is solvable).
    (repo / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef divide(a, b):\n    return a / b\n")
    pt2 = subprocess.run(["python", "-m", "pytest", "-q"], cwd=repo,
                         capture_output=True, text=True, check=False)
    assert pt2.returncode == 0


def test_classification_maps_outcomes() -> None:
    solved = VendorRunResult(harness="codex_cli", version="x", no_patch_solve=True)
    assert _classify_vendor(solved) == "task_success"
    timed = VendorRunResult(harness="codex_cli", version="x", timed_out=True,
                            error="timeout")
    assert _classify_vendor(timed) == "infra_timeout_before_action"  # inconclusive
    leaked = VendorRunResult(harness="codex_cli", version="x", no_patch_solve=True,
                             secret_leak=True)
    assert _classify_vendor(leaked) == "task_failure"


def test_openhands_capability_level_reported() -> None:
    lvl = openhands_capability_level()
    assert lvl["available"] is True and lvl["level"] >= 1  # installed -> >= health


def test_unknown_harness_rejected() -> None:
    import pytest
    with pytest.raises(ValueError):
        VendorNativeHarness("not_a_harness")
    assert VendorNativeHarness("codex_cli").spec.binary == "codex"


def test_specs_have_argv_for_task_runners() -> None:
    assert VENDOR_SPECS["codex_cli"].argv_fn is not None
    assert VENDOR_SPECS["claude_code"].argv_fn is not None
    assert VENDOR_SPECS["openhands"].argv_fn is None  # health-check only


def test_vendor_cell_classifies_via_measurement_trust() -> None:
    # WS11: a VendorRunResult maps to a measurement-trust cell that the real classifier
    # agrees with (success conclusive; timeout infra/inconclusive).
    from acp.evaluation.learning_gate import eligible_for_quality
    from acp.evaluation.measurement_hygiene import classify_attempt

    solved = VendorRunResult(harness="codex_cli", version="x", no_patch_solve=True,
                             pytest_passed=True, diff_captured=True)
    cell = solved.to_cell()
    assert classify_attempt(cell).value == "task_success"
    assert eligible_for_quality(cell)  # conclusive success updates quality

    timed = VendorRunResult(harness="codex_cli", version="x", timed_out=True,
                            error="timeout")
    tcell = timed.to_cell()
    assert classify_attempt(tcell).is_infra and not eligible_for_quality(tcell)


def test_skill_injection_fields_default_and_set() -> None:
    # WS10: skill injection writes SKILL.md + records injected/used.
    r = VendorRunResult(harness="codex_cli", version="x")
    assert r.skill_injected is False and r.skill_used_observed == "unknown"
