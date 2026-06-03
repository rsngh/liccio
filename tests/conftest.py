"""Shared pytest fixtures and deterministic-test setup."""

from __future__ import annotations

import os
import random
from collections.abc import Iterator

import pytest

from acp.core.config import ACPSettings, reset_settings

SEED = 1234


@pytest.fixture(autouse=True)
def _deterministic_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """Seed RNGs and reset cached settings for every test."""
    random.seed(SEED)
    monkeypatch.setenv("ACP_APP_ENV", "test")
    # Prevent embedder/key pollution leaking between tests: a live test may write
    # ACP_OPENAI_API_KEY / ACP_EMBEDDER straight into os.environ, which would
    # otherwise make later tests' auto-selected embedder non-deterministic (and
    # incur real API calls). monkeypatch restores the original after each test.
    monkeypatch.delenv("ACP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ACP_EMBEDDER", raising=False)
    # Redirect the human-label eval-case export off the committed fixture so a
    # test exercising make_eval_case never mutates evals/datasets/*.jsonl.
    monkeypatch.setenv(
        "ACP_EVAL_CASES_PATH", str(tmp_path_factory.mktemp("evalcases") / "cases.jsonl")
    )
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        artifact_dir=tmp_path / "artifacts",
        workspace_dir=tmp_path / "workspaces",
    )


@pytest.fixture
def live_enabled() -> bool:
    """True when real API keys are present (gates live-marked tests)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))
