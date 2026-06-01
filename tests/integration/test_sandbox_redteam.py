"""Sandbox red-team lab (round-5 WS10)."""

from __future__ import annotations

from acp.evaluation.sandbox_redteam import (
    run_docker_redteam,
    run_local_redteam,
    run_sandbox_redteam,
)


def test_local_enforces_containment_probes(tmp_path) -> None:
    rep = run_local_redteam(tmp_path / "ws")
    by_attack = {c["attack"]: c for c in rep["enforced_checks"]}
    # the protections that DO exist locally must hold
    assert by_attack["env_exfiltration"]["enforced"] is True
    assert by_attack["write_outside_workspace"]["enforced"] is True
    assert by_attack["parent_directory_read"]["enforced"] is True
    assert by_attack["symlink_escape"]["enforced"] is True


def test_local_marked_unsafe_for_true_harness(tmp_path) -> None:
    rep = run_local_redteam(tmp_path / "ws")
    assert rep["unsafe_for_true_harness"] is True
    assert rep["reason"]
    # network + resource attacks are explicitly listed as not enforceable locally
    assert {"network_exfiltration", "fork_bomb", "memory_bomb"}.issubset(
        set(rep["not_enforceable"]))


def test_docker_section_explicit_when_unavailable() -> None:
    rep = run_docker_redteam()
    assert rep["backend"] == "docker"
    assert rep["status"] in ("skipped", "available")
    if rep["status"] == "skipped":
        assert rep["reason"]


def test_full_report_conclusion(tmp_path) -> None:
    rep = run_sandbox_redteam(tmp_path / "ws")
    assert "local" in rep and "docker" in rep
    assert "UNSAFE" in rep["conclusion"]
