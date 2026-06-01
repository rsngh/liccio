"""Security red-team (charter §21.9): malicious tasks must not exfiltrate/escape."""

from __future__ import annotations

import sys

import pytest

from acp.core.errors import CommandSecurityError
from acp.core.redaction import Redactor
from acp.workspaces.command_runner import CommandRunner


@pytest.fixture
def runner(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    return CommandRunner(allowed_root=root), root


def test_redteam_cannot_escape_workspace(runner, tmp_path) -> None:
    cr, _root = runner
    outside = tmp_path / "outside"
    outside.mkdir()
    # attempt to run a command outside the sandbox root
    with pytest.raises(CommandSecurityError):
        cr.run([sys.executable, "-c", "print('pwned')"], cwd=outside)


def test_redteam_env_secrets_never_in_output(runner) -> None:
    cr, root = runner
    # malicious: print all env vars hoping to leak the API key
    rec = cr.run(
        [sys.executable, "-c", "import os; print(dict(os.environ))"],
        cwd=root,
        env={"PATH": "/usr/bin", "ACP_OPENAI_API_KEY": "sk-super-secret-key-999"},
    )
    assert "sk-super-secret-key-999" not in rec.stdout_summary


def test_redteam_print_secret_redacted(runner) -> None:
    cr, root = runner
    rec = cr.run(
        [sys.executable, "-c", "print('exfil: sk-ant-abcdefghijklmnopqrstuvwx')"],
        cwd=root,
    )
    assert "sk-ant-abcdefghijklmnopqrstuvwx" not in rec.stdout_summary


def test_redteam_network_denied_by_default() -> None:
    from acp.core.policies import PolicyEngine

    assert PolicyEngine().network_allowed() is False


def test_redteam_auto_merge_disabled_and_high_risk_gated() -> None:
    from acp.core.enums import RiskLevel
    from acp.core.errors import PolicyViolation
    from acp.core.policies import PolicyEngine

    eng = PolicyEngine()
    assert eng.can_auto_merge() is False
    # a "modify policy to auto-approve" attempt is blocked for high risk
    with pytest.raises(PolicyViolation):
        eng.check_auto_finalize(RiskLevel.CRITICAL, experimental=False)


def test_redteam_secret_files_not_indexed(tmp_path) -> None:
    from acp.context.indexer import RepoIndexer

    (tmp_path / ".env").write_text("ACP_OPENAI_API_KEY=sk-leak-me")
    (tmp_path / "id_rsa").write_text("PRIVATE KEY MATERIAL")
    (tmp_path / "app.py").write_text("x = 1\n")
    idx = RepoIndexer(tmp_path, "r", "s").index()
    paths = {c.path for c in idx.chunks}
    assert ".env" not in paths
    assert "id_rsa" not in paths
    # and no secret content leaked into any chunk
    assert all("sk-leak-me" not in c.content for c in idx.chunks)


def test_redaction_helper_covers_common_shapes() -> None:
    r = Redactor()
    for secret in ("sk-ant-aaaaaaaaaaaaaaaaaaaa", "ghp_aaaaaaaaaaaaaaaaaaaaaa",
                   "AKIA1234567890ABCDEF"):
        assert "***REDACTED***" in r.redact_text(f"leak {secret} here")
