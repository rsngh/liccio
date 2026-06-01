"""Live multi-harness bakeoff: OpenAI vs Claude on the SAME no-patch task.

Skipped unless both keys + SDKs are present. This is the central Alpha-4
experiment: two real harnesses, same task, normalized traces compared.
"""

from __future__ import annotations

import os

import pytest

from acp.evaluation.multi_harness_bakeoff import NoPatchTask, run_multi_harness_bakeoff

pytestmark = [pytest.mark.live, pytest.mark.live_second_harness]


def _have(mod: str, key: str) -> bool:
    try:
        __import__(mod)
    except Exception:
        return False
    return bool(os.environ.get(key))


@pytest.mark.skipif(
    not (_have("openai", "OPENAI_API_KEY") and _have("anthropic", "ANTHROPIC_API_KEY")),
    reason="needs both OPENAI_API_KEY+openai and ANTHROPIC_API_KEY+anthropic")
def test_two_real_harnesses_compared_on_same_task() -> None:
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    from acp.core.config import reset_settings
    reset_settings()
    from acp.agents.claude_harness import ClaudeHarnessAdapter
    from acp.agents.openai_harness import OpenAIHarnessAdapter

    task = [NoPatchTask("bugfix", "Fix divide by zero",
                        "divide() returns 0 on a zero divisor; it must raise "
                        "ZeroDivisionError. Edit calculator.py.",
                        ["divide(x, 0) raises ZeroDivisionError"])]
    report = run_multi_harness_bakeoff(
        {"openai_harness": lambda: OpenAIHarnessAdapter(max_steps=6),
         "claude_harness": lambda: ClaudeHarnessAdapter(max_steps=6)}, tasks=task)
    comp = report["comparison"]
    assert set(comp) == {"openai_harness", "claude_harness"}
    # both are true harnesses and both should make tool calls
    assert comp["openai_harness"]["is_harness"] and comp["claude_harness"]["is_harness"]
    assert all(c["tool_calls"] >= 1 for c in report["cells"])
    # at least one real harness solves the bug with no supplied patch
    assert report["summary"]["solved"] >= 1
