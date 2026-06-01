"""Command-runner hardening (round-1 two-day D1B4 / §C)."""

from __future__ import annotations

import os
import sys

import pytest

from acp.core.errors import CommandSecurityError
from acp.workspaces.command_runner import CommandRunner


def test_prefix_escape_blocked(tmp_path) -> None:
    # A sibling dir sharing a name prefix must not be considered "inside".
    root = tmp_path / "ws"
    root.mkdir()
    sibling = tmp_path / "ws_evil"
    sibling.mkdir()
    r = CommandRunner(allowed_root=root)
    with pytest.raises(CommandSecurityError):
        r.run([sys.executable, "-c", "print(1)"], cwd=sibling)


def test_symlink_escape_blocked(tmp_path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    r = CommandRunner(allowed_root=root)
    # resolve() follows the symlink to `outside`, which is outside the root.
    with pytest.raises(CommandSecurityError):
        r.run([sys.executable, "-c", "print(1)"], cwd=link)


def test_max_output_override_does_not_mutate_runner(tmp_path) -> None:
    r = CommandRunner(allowed_root=tmp_path, max_output_chars=20_000)
    r.run([sys.executable, "-c", "print('x'*100)"], cwd=tmp_path, max_output_chars=10)
    assert r.max_output_chars == 20_000  # instance state unchanged


def test_audit_hook_fires_on_elevated_request(tmp_path) -> None:
    events = []
    r = CommandRunner(allowed_root=tmp_path, audit_hook=lambda e, d: events.append((e, d)))
    r.run([sys.executable, "-c", "print(1)"], cwd=tmp_path, allow_network=True)
    assert any(e == "command_elevated_request" and d["network"] for e, d in events)


def test_no_env_secret_in_child_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ACP_SECRET_TOKEN", "sk-do-not-leak-123")
    r = CommandRunner(allowed_root=tmp_path)
    rec = r.run([sys.executable, "-c", "import os;print(os.environ.get('ACP_SECRET_TOKEN'))"],
                cwd=tmp_path)
    assert "ACP_SECRET_TOKEN" not in rec.sanitized_env_keys
    assert "sk-do-not-leak-123" not in rec.stdout_summary
    assert "None" in rec.stdout_summary  # child didn't receive it
    os.environ.pop("ACP_SECRET_TOKEN", None)
