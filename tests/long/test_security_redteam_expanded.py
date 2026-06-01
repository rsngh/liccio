"""Expanded security red-team (round-2 Block E).

Covers escape attempts, argv injection, secret exfiltration, oversized output,
and adversarial-diff detection. Local controls are asserted directly; hard
network/FS isolation is the Docker backend's job (tested in Block D).
"""

from __future__ import annotations

import sys

import pytest

from acp.core.errors import CommandSecurityError
from acp.workspaces.command_runner import CommandRunner


@pytest.fixture
def runner(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    return CommandRunner(allowed_root=root, max_output_chars=2000), root


def test_symlink_escape_blocked(runner, tmp_path) -> None:
    cr, root = runner
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "esc"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(CommandSecurityError):
        cr.run([sys.executable, "-c", "print(1)"], cwd=link)


def test_parent_dir_cwd_escape_blocked(runner, tmp_path) -> None:
    cr, root = runner
    with pytest.raises(CommandSecurityError):
        cr.run([sys.executable, "-c", "print(1)"], cwd=root.parent)


def test_prefix_sibling_escape_blocked(runner, tmp_path) -> None:
    cr, root = runner
    sibling = root.parent / (root.name + "_evil")
    sibling.mkdir()
    with pytest.raises(CommandSecurityError):
        cr.run([sys.executable, "-c", "print(1)"], cwd=sibling)


def test_shell_metacharacters_in_argv_are_literal(runner) -> None:
    cr, root = runner
    # argv (no shell) -> metacharacters are literal args, not interpreted
    rec = cr.run([sys.executable, "-c", "import sys; print(sys.argv[1])", "; rm -rf /"],
                 cwd=root)
    assert rec.exit_code == 0
    assert "; rm -rf /" in rec.stdout_summary


def test_env_secret_not_in_child(runner) -> None:
    cr, root = runner
    rec = cr.run([sys.executable, "-c", "import os;print(os.environ.get('ACP_API_KEY'))"],
                 cwd=root, env={"PATH": "/usr/bin", "ACP_API_KEY": "sk-redteam-secret-1"})
    assert "ACP_API_KEY" not in rec.sanitized_env_keys
    assert "sk-redteam-secret-1" not in rec.stdout_summary
    assert "None" in rec.stdout_summary


def test_printed_secret_is_redacted(runner) -> None:
    cr, root = runner
    rec = cr.run([sys.executable, "-c", "print('leak sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa')"], cwd=root)
    assert "sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa" not in rec.stdout_summary


def test_massive_stdout_truncated(tmp_path) -> None:
    from acp.core.artifacts import LocalArtifactStore

    store = LocalArtifactStore(tmp_path / "art")
    cr = CommandRunner(artifact_store=store, allowed_root=tmp_path, max_output_chars=500)
    rec = cr.run([sys.executable, "-c", "print('A'*200000)"], cwd=tmp_path)
    assert len(rec.stdout_summary) < 5000  # bounded
    assert rec.stdout_artifact_ref is not None  # full output preserved as artifact


def test_network_request_audited_not_default(runner) -> None:
    cr, root = runner
    events = []
    cr.audit_hook = lambda e, d: events.append((e, d))
    rec = cr.run([sys.executable, "-c", "print(1)"], cwd=root, allow_network=True)
    assert rec.allow_network is True
    assert any(e == "command_elevated_request" for e, _ in events)
    # default is no network
    assert CommandRunner(allowed_root=root).run(
        [sys.executable, "-c", "print(1)"], cwd=root
    ).allow_network is False


def test_adversarial_diff_flags_delete_tests_and_disable() -> None:
    from acp.schemas.workspace import DiffBundle
    from acp.verification.adversarial import has_high_severity, scan_diff

    diff = DiffBundle(
        unified_diff="-def test_core():\n-    assert x == 1\n+    pytest.skip('disabled')\n",
        changed_files=["m.py"], deleted_files=["tests/test_core.py"],
    )
    findings = scan_diff(diff)
    codes = {f.code for f in findings}
    assert "deleted_test" in codes
    assert "removed_test_fn" in codes or "weakened_assertions" in codes
    assert "added_skip" in codes
    assert has_high_severity(findings)
