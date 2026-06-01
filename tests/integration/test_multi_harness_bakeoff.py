"""Multi-harness no-patch bakeoff (round-4 Block F)."""

from __future__ import annotations

import time

import pytest

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import AgentKind
from acp.evaluation.multi_harness_bakeoff import NoPatchTask, run_multi_harness_bakeoff
from acp.schemas.agent import AgentAttemptResult, AgentHealth, AgentPlan, AgentReviewResult
from acp.workspaces.command_runner import CommandRunner

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"

TWO_TASKS = [
    NoPatchTask("bugfix", "Fix divide by zero",
                "divide() must raise ZeroDivisionError on zero divisor.",
                ["divide(x, 0) raises"]),
    NoPatchTask("refactor", "Clarify divide",
                "Refactor divide() for clarity.", ["behaviour unchanged"]),
]


class ScriptedHarness:
    """A true harness that deterministically fixes the calculator bug."""

    kind = AgentKind.SIMPLE_LLM
    is_harness = True
    name = "scripted_harness"

    async def healthcheck(self):
        return AgentHealth(name=self.name, kind=self.kind, available=True, detail="ok")

    async def plan(self, *a, **k):
        return AgentPlan(summary="fix")

    async def execute(self, task, context_pack, workspace, budget) -> AgentAttemptResult:
        from pathlib import Path

        from acp.agents.harness_base import HarnessTools
        from acp.workspaces.diff import DiffCapturer
        t0 = time.monotonic()
        runner = CommandRunner(allowed_root=Path(workspace.path), scrub_secrets=True)
        tools = HarnessTools(workspace=workspace, runner=runner)
        tools.read_file("calculator.py")
        tools.write_file("calculator.py", FIXED)
        cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
        from acp.schemas.agent import DiffBundleRef
        return AgentAttemptResult(
            status="succeeded",
            diff=DiffBundleRef(unified_diff=cap.get_unified_diff(),
                               changed_files=cap.get_changed_files()),
            input_token_count=10, output_token_count=10, estimated_cost_usd=0.0001,
            tool_calls=tools.tool_calls, wall_time_s=time.monotonic() - t0,
            metadata={"session_id": "scripted-1"})

    async def review(self, *a, **k):
        return AgentReviewResult(verdict="pass", score=1.0, confidence=0.5)


class DoNothingFake:
    """A baseline adapter that never edits anything -> never solves."""

    kind = AgentKind.FAKE
    is_harness = False
    name = "fake"

    async def healthcheck(self):
        return AgentHealth(name=self.name, kind=self.kind, available=True, detail="ok")

    async def plan(self, *a, **k):
        return AgentPlan(summary="noop")

    async def execute(self, task, context_pack, workspace, budget) -> AgentAttemptResult:
        return AgentAttemptResult(status="succeeded")  # no diff -> verification fails

    async def review(self, *a, **k):
        return AgentReviewResult(verdict="uncertain", confidence=0.1)


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'f.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_no_patch_bakeoff_rejects_metadata_files() -> None:
    bad = [NoPatchTask("x", "t", "b", metadata={"files": {"calculator.py": FIXED}})]
    with pytest.raises(ValueError, match="files"):
        run_multi_harness_bakeoff({"scripted_harness": ScriptedHarness}, tasks=bad)


def test_multi_harness_bakeoff_persists_agent_traces(service) -> None:
    run = service.run_multi_harness_bakeoff(
        {"scripted_harness": ScriptedHarness}, tasks=TWO_TASKS)
    assert run.kind == "multi_harness_bakeoff"
    # durable: a fresh service reads the report + cases from the DB
    fresh = AppService(service.settings)
    report = fresh.get_eval_report(run.id)["content"]
    assert report["cells"], "no cells persisted"
    assert all(c["tool_calls"] >= 1 for c in report["cells"]), "traces not captured"
    assert all("calculator.py" in c["file_writes"] for c in report["cells"])


def test_bakeoff_compares_trace_metrics() -> None:
    report = run_multi_harness_bakeoff(
        {"scripted_harness": ScriptedHarness, "fake": DoNothingFake}, tasks=TWO_TASKS)
    comp = report["comparison"]
    assert set(comp) == {"scripted_harness", "fake"}
    # the true harness is distinguishable: it makes tool calls, the fake does not
    assert comp["scripted_harness"]["is_harness"] is True
    assert comp["fake"]["is_harness"] is False
    assert comp["scripted_harness"]["mean_tool_calls"] >= 1
    assert comp["fake"]["mean_tool_calls"] == 0
    # and it actually solves while the no-op baseline does not
    assert comp["scripted_harness"]["solve_rate"] > comp["fake"]["solve_rate"]


def test_bakeoff_failure_taxonomy() -> None:
    report = run_multi_harness_bakeoff({"fake": DoNothingFake}, tasks=TWO_TASKS)
    # the no-op baseline fails verification -> a non-"none" failure class recorded
    assert report["failure_taxonomy"]
    assert any(k != "none" for k in report["failure_taxonomy"])
    assert report["summary"]["solve_rate"] < 1.0
