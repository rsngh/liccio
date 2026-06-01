"""Shared pytest fixtures and deterministic-test setup."""

from __future__ import annotations

import os
import random
from collections.abc import Iterator

import pytest

from acp.core.config import ACPSettings, reset_settings

SEED = 1234


@pytest.fixture(autouse=True)
def _deterministic_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Seed RNGs and reset cached settings for every test."""
    random.seed(SEED)
    monkeypatch.setenv("ACP_APP_ENV", "test")
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
