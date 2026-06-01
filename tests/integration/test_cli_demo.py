"""CLI demo tests (charter §19, §20)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from acp.cli.main import app
from acp.core.config import reset_settings

runner = CliRunner()


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("ACP_ARTIFACT_DIR", str(tmp_path / "art"))
    monkeypatch.setenv("ACP_WORKSPACE_DIR", str(tmp_path / "ws"))
    reset_settings()
    yield
    reset_settings()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "demo" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "acp" in result.output


def test_demo_bugfix_end_to_end(cli_env) -> None:
    result = runner.invoke(app, ["demo", "bugfix"])
    assert result.exit_code == 0, result.output
    assert "succeeded" in result.output


def test_demo_quickstart(cli_env) -> None:
    result = runner.invoke(app, ["demo", "quickstart"])
    assert result.exit_code == 0, result.output
    assert "trace_id" in result.output


def test_demo_bandit() -> None:
    result = runner.invoke(app, ["demo", "bandit", "--rounds", "500"])
    assert result.exit_code == 0, result.output
    assert "beats_random" in result.output
