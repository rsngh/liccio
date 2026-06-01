"""Multi-adapter trace bakeoff (round-3 R3-5)."""

from __future__ import annotations

import time

from acp.agents.fake import FakeAgentAdapter
from acp.agents.openai_harness import HarnessTools
from acp.agents.patch_agent import PatchAgentAdapter
from acp.core.enums import AgentKind, RunStatus
from acp.evaluation.trace_bakeoff import run_trace_bakeoff
from acp.schemas.agent import (
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    DiffBundleRef,
)
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.diff import DiffCapturer

FIX = ("def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError('x')\n"
       "    return a / b\n")


class ScriptedHarness:
    kind = AgentKind.SIMPLE_LLM
    is_harness = True
    name = "scripted_harness"

    async def healthcheck(self) -> AgentHealth:
        return AgentHealth(name=self.name, kind=self.kind, available=True)

    async def plan(self, task, context_pack, workspace, budget) -> AgentPlan:
        return AgentPlan(summary="scripted")

    async def execute(self, task, context_pack, workspace, budget) -> AgentAttemptResult:
        t0 = time.monotonic()
        tools = HarnessTools(workspace=workspace,
                             runner=CommandRunner(allowed_root=workspace.path))
        tools.read_file("calculator.py")
        tools.write_file("calculator.py", FIX)
        cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
        return AgentAttemptResult(
            status=RunStatus.SUCCEEDED,
            diff=DiffBundleRef(unified_diff=cap.get_unified_diff(),
                               changed_files=cap.get_changed_files()),
            input_token_count=10, output_token_count=10, tool_calls=tools.tool_calls,
            wall_time_s=time.monotonic() - t0, metadata={"session_id": "scripted-1"},
        )

    async def review(self, task, diff, context_pack, budget) -> AgentReviewResult:
        return AgentReviewResult(verdict="pass", score=1.0, confidence=0.5)


def test_trace_bakeoff_compares_adapters() -> None:
    report = run_trace_bakeoff({
        "patch": PatchAgentAdapter,
        "fake": FakeAgentAdapter,
        "scripted_harness": ScriptedHarness,
    })
    adapters = report["adapters"]
    assert set(adapters) == {"patch", "fake", "scripted_harness"}

    # only the true harness actually solves the no-patch bug
    assert "scripted_harness" in report["summary"]["solved"]
    assert "scripted_harness" in report["summary"]["harness_adapters"]
    assert adapters["scripted_harness"]["tool_calls"] >= 2
    assert "calculator.py" in adapters["scripted_harness"]["file_writes"]

    # patch/fake have no pre-supplied patch -> they do not solve it
    assert not adapters["patch"]["solved"]
    assert not adapters["fake"]["solved"]
    # traces are directly comparable (same shape) across all adapters
    for r in adapters.values():
        assert set(r) >= {"tool_calls", "commands", "file_writes", "solved", "is_harness"}
