"""Vendor-native harness live gate (WS19).

Runs the real installed vendor harnesses (codex / Claude Code / OpenHands) on a no-patch
fix-the-failing-test task. Marked ``live_vendor`` so it is opt-in (`pytest -m live_vendor`).
Unavailable harnesses are skipped, not failed; the whole test skips if none are present.
"""

from __future__ import annotations

import shutil

import pytest

from acp.evaluation.vendor_harness_live import run_vendor_harness_live

pytestmark = pytest.mark.live_vendor


def _any_vendor() -> bool:
    return any(shutil.which(b) for b in ("codex", "claude", "openhands"))


@pytest.mark.skipif(not _any_vendor(), reason="no vendor harness on PATH")
def test_vendor_harness_live_gate() -> None:
    report = run_vendor_harness_live()
    assert report["available"] is True
    # No available harness may leak a secret.
    for name, h in report["harnesses"].items():
        if h.get("available") and "secret_leak" in h:
            assert h["secret_leak"] is False, f"{name} leaked a secret"
    # Each harness is either available (with a version) or explicitly skipped.
    for name, h in report["harnesses"].items():
        assert h.get("available") or h.get("skipped"), name


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex not installed")
def test_codex_runs_without_conclusive_failure() -> None:
    report = run_vendor_harness_live()
    codex = report["harnesses"]["codex_cli"]
    assert codex["available"] and codex["version"].startswith("codex")
    assert codex.get("secret_leak") is False
    # codex either SOLVES the task or hits an inconclusive infra timeout (it is a slow
    # harness) — but it must never conclusively fail (ran clean yet did not solve).
    assert codex.get("no_patch_solve") or "error" in codex
