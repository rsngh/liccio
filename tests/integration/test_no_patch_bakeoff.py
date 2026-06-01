"""Real (no pre-supplied patch) agent bakeoff (round-3 R3-4)."""

from __future__ import annotations

import time

import pytest
from git import Repo

from acp.agents.openai_harness import HarnessTools
from acp.agents.registry import AgentRegistry
from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import AgentKind, RunStatus
from acp.evaluation.bakeoff import run_no_patch_bakeoff
from acp.schemas.agent import AgentAttemptResult, AgentHealth, AgentPlan, AgentReviewResult
from acp.workspaces.command_runner import CommandRunner

FIX = ("def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError('division by zero')\n"
       "    return a / b\n")


class ScriptedHarness:
    """Deterministic true-harness stand-in: reads then writes the fix via tools,
    producing a real captured trace — no pre-supplied patch."""

    kind = AgentKind.SIMPLE_LLM
    is_harness = True
    name = "scripted_harness"

    async def healthcheck(self) -> AgentHealth:
        return AgentHealth(name=self.name, kind=self.kind, available=True)

    async def plan(self, task, context_pack, workspace, budget) -> AgentPlan:
        return AgentPlan(summary="scripted")

    async def execute(self, task, context_pack, workspace, budget) -> AgentAttemptResult:
        t0 = time.monotonic()
        runner = CommandRunner(allowed_root=workspace.path, scrub_secrets=True)
        tools = HarnessTools(workspace=workspace, runner=runner)
        tools.read_file("calculator.py")
        tools.write_file("calculator.py", FIX)
        from acp.schemas.agent import DiffBundleRef
        from acp.workspaces.diff import DiffCapturer

        cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
        return AgentAttemptResult(
            status=RunStatus.SUCCEEDED,
            diff=DiffBundleRef(unified_diff=cap.get_unified_diff(),
                               changed_files=cap.get_changed_files()),
            input_token_count=10, output_token_count=10,
            tool_calls=tools.tool_calls, wall_time_s=time.monotonic() - t0,
            metadata={"session_id": "scripted-1"},
        )

    async def review(self, task, diff, context_pack, budget) -> AgentReviewResult:
        return AgentReviewResult(verdict="pass", score=1.0, confidence=0.5)


@pytest.fixture
def service(tmp_path) -> AppService:
    reg = AgentRegistry()
    reg.register(ScriptedHarness())  # only agent -> routing must select it
    return AppService(
        ACPSettings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'np.db'}",
                    artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"),
        registry=reg,
    )


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    # test fails unless the zero-division bug is actually fixed (no-op won't pass)
    (src / "test_calculator.py").write_text(
        "import pytest\nfrom calculator import divide\n\n\n"
        "def test_zero():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "np"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("np", str(src), default_branch="master")


def test_no_patch_bakeoff_solved_by_harness(service, tmp_path) -> None:
    repo = _repo(service, tmp_path)
    report = run_no_patch_bakeoff(service, repo.id, n=2)
    assert report["mode"] == "no_patch"
    assert report["summary"]["solve_rate"] == 1.0  # solved without any supplied patch
    cell = report["cells"][0]
    assert cell["agent"] == "scripted_harness"
    assert cell["tool_calls"] >= 2  # read + write captured
    assert "calculator.py" in cell["file_writes"]
