"""Shared pytest fixtures and deterministic-test setup."""

from __future__ import annotations

import os
import random
from collections.abc import Iterator

import pytest

from acp.core.config import ACPSettings, reset_settings

SEED = 1234

# Provider credentials that would let a test reach a live model/embedding API.
# The deterministic suite must never touch any of these (charter: offline tests
# never call live providers even if keys are set).
_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ACP_OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ACP_ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "ACP_GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() not in {"", "0", "false", "no"}


def pytest_configure(config: pytest.Config) -> None:
    """Offline guard, run before any test module is imported.

    Unless ``ACP_TEST_LIVE`` is set, provider API keys are stripped from the
    environment *here* (at configure time, before collection) so module-level
    ``LIVE = bool(os.environ.get(...))`` sentinels and ``skipif`` decorators in the
    live tests see no keys and skip cleanly — the deterministic suite can never
    reach a live provider even on a developer machine that has keys exported.

    With ``ACP_STRICT_OFFLINE`` set (used by the offline CI job), a leaked key is a
    hard error instead of being silently stripped, so misconfiguration fails fast.
    """
    if _truthy(os.environ.get("ACP_TEST_LIVE")):
        return  # live mode: the caller opted in, keep the keys
    present = [k for k in _PROVIDER_KEYS if os.environ.get(k)]
    if not present:
        return
    if _truthy(os.environ.get("ACP_STRICT_OFFLINE")):
        raise pytest.UsageError(
            "offline test run but provider keys are present: "
            f"{', '.join(sorted(present))}. Unset them, or run a `make test-live-*` "
            "target (which sets ACP_TEST_LIVE=1)."
        )
    for key in present:
        os.environ.pop(key, None)


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
