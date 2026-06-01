"""CommandRunner tests (charter §9.2)."""

from __future__ import annotations

import sys

import pytest

from acp.core.artifacts import LocalArtifactStore
from acp.core.errors import CommandSecurityError
from acp.workspaces.command_runner import CommandRunner


def test_success_returns_exit_zero(tmp_path) -> None:
    r = CommandRunner(allowed_root=tmp_path)
    rec = r.run([sys.executable, "-c", "print('hi')"], cwd=tmp_path)
    assert rec.exit_code == 0
    assert "hi" in rec.stdout_summary
    assert not rec.timed_out


def test_failing_command_nonzero_no_raise(tmp_path) -> None:
    r = CommandRunner(allowed_root=tmp_path)
    rec = r.run([sys.executable, "-c", "import sys; sys.exit(3)"], cwd=tmp_path)
    assert rec.exit_code == 3


def test_timeout_terminates(tmp_path) -> None:
    r = CommandRunner(allowed_root=tmp_path)
    rec = r.run([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path, timeout_s=1)
    assert rec.timed_out is True
    assert rec.exit_code is None


def test_cwd_containment(tmp_path) -> None:
    r = CommandRunner(allowed_root=tmp_path / "root")
    (tmp_path / "root").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(CommandSecurityError):
        r.run([sys.executable, "-c", "print(1)"], cwd=outside)


def test_env_secrets_redacted(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path / "art")
    r = CommandRunner(artifact_store=store, allowed_root=tmp_path)
    rec = r.run(
        [sys.executable, "-c", "print('sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa')"],
        cwd=tmp_path,
        env={"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-secret-value-123456"},
    )
    # secret env key is recorded by name only; value never stored
    assert "OPENAI_API_KEY" in rec.sanitized_env_keys
    assert "sk-secret-value-123456" not in rec.stdout_summary
    # secret-shaped stdout is redacted
    assert "sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa" not in rec.stdout_summary


def test_large_output_truncated_and_artifacted(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path / "art")
    r = CommandRunner(artifact_store=store, allowed_root=tmp_path, max_output_chars=200)
    rec = r.run(
        [sys.executable, "-c", "print('A' * 5000)"],
        cwd=tmp_path,
    )
    assert rec.stdout_artifact_ref is not None
    assert len(rec.stdout_summary) < 5000


def test_command_not_found(tmp_path) -> None:
    r = CommandRunner(allowed_root=tmp_path)
    rec = r.run(["definitely-not-a-real-binary-xyz"], cwd=tmp_path)
    assert rec.exit_code == 127
