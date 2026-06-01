"""Live skeletons for Claude/Codex/OpenHands adapters (round-1 D2B6).

All skipped unless the relevant SDK/binary/keys are present. They assert that an
unavailable adapter explains itself rather than crashing.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from acp.agents.claude_agent import ClaudeAgentAdapter
from acp.agents.codex_agent import CodexAgentAdapter
from acp.agents.openhands_agent import OpenHandsAgentAdapter

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY")
def test_claude_health_explains() -> None:
    h = asyncio.run(ClaudeAgentAdapter().healthcheck())
    assert isinstance(h.available, bool)
    assert h.detail  # explains availability either way


def test_codex_health_never_crashes() -> None:
    h = asyncio.run(CodexAgentAdapter().healthcheck())
    assert isinstance(h.available, bool)
    assert h.detail


def test_openhands_health_never_crashes() -> None:
    h = asyncio.run(OpenHandsAgentAdapter().healthcheck())
    assert isinstance(h.available, bool)
    assert h.detail
