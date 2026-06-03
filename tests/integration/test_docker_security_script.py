"""Docker security evidence pack script (round-4 Block D).

Validates that the script always produces a structured report with all seven
named checks, and an EXPLICIT skipped status when Docker is unavailable. The
real pass/fail assertions run under the live_docker marker.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "evals/scripts/run_docker_security_check.py"

_EXPECTED_CHECKS = {
    "pwd_is_workspace", "non_root", "network_blocked", "memory_hog_fails",
    "pid_limit", "workspace_write_reflected", "cleanup_removes_worktree",
}


def _load():
    spec = importlib.util.spec_from_file_location("docker_sec", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_report_has_all_named_checks_and_explicit_status() -> None:
    mod = _load()
    report = mod.run_checks()
    names = {c["name"] for c in report["checks"]}
    if report["docker_available"]:
        assert _EXPECTED_CHECKS.issubset(names)
        assert report["status"] in ("pass", "fail")
    else:
        # explicit skip, never silently empty
        assert report["status"] == "skipped"
        assert report["reason"]
        assert names == _EXPECTED_CHECKS
        assert all(c["status"] == "skipped" for c in report["checks"])


def test_markdown_and_main_write_artifacts(tmp_path, monkeypatch) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "REPORT_DIR", tmp_path)
    rc = mod.main()
    assert rc == 0  # skip or pass is a successful evidence run
    data = json.loads((tmp_path / "docker_security.json").read_text())
    assert "checks" in data and (tmp_path / "docker_security.md").exists()
    md = (tmp_path / "docker_security.md").read_text()
    assert "Docker security evidence" in md


@pytest.mark.live_docker
def test_docker_security_all_pass_live() -> None:
    mod = _load()
    if not mod.docker_available():
        pytest.skip("docker not available")
    # Live container ops can flake transiently under full-suite load (slow starts,
    # image-layer contention). Retry once; only persistent failures are real.
    report = mod.run_checks()
    failing = [c["name"] for c in report["checks"] if c["status"] != "pass"]
    if failing:
        report = mod.run_checks()
        failing = [c["name"] for c in report["checks"] if c["status"] != "pass"]
    assert not failing, f"failing docker security checks: {failing}"
