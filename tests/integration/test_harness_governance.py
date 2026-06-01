"""Harness governance enforcement in orchestration (round-4 Block B).

The execution-backend policy is wired into the agent-launch path:
  true harness + local            => blocked (failed attempt + audit)
  true harness + local override   => allowed + audit
  true harness + docker           => allowed
  simple model + local            => allowed + warning audit
  fake/patch    + local           => allowed (no audit)
"""

from __future__ import annotations

import pytest
from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import AgentKind
from acp.schemas.agent import AgentAttemptResult, AgentHealth, DiffBundleRef


class _StubAdapter:
    """A minimal adapter whose harness/kind flags we control."""

    def __init__(self, name, kind, is_harness, write=True):
        self.name = name
        self.kind = kind
        self.is_harness = is_harness
        self._write = write

    async def healthcheck(self):
        return AgentHealth(name=self.name, kind=self.kind, available=True, detail="ok")

    async def plan(self, *a, **k):
        from acp.schemas.agent import AgentPlan
        return AgentPlan(summary="plan")

    async def execute(self, task, context_pack, workspace, budget) -> AgentAttemptResult:
        # touch a file so a non-blocked run "succeeds"
        if self._write:
            from pathlib import Path
            (Path(workspace.path) / "calculator.py").write_text(
                "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n"
                "    return a / b\n")
        return AgentAttemptResult(
            status="succeeded",
            diff=DiffBundleRef(unified_diff="+x\n", changed_files=["calculator.py"]))

    async def review(self, *a, **k):
        from acp.schemas.agent import AgentReviewResult
        return AgentReviewResult(verdict="uncertain", confidence=0.1)


def _make_service(tmp_path, adapter, *, backend="local", allow_local_harness=False):
    from acp.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.register(adapter)
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'g.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
        workspace_backend=backend, allow_local_harness=allow_local_harness,
    ), registry=reg)


def _make_repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "pyproject.toml").write_text(
        '[project]\nname = "g"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n')
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("g", str(src), default_branch="master")


def _audit_types(svc, run_id):
    graph = AppService(svc.settings).full_run_graph(run_id)
    return [e["event_type"] for e in graph["audit_events"]], graph


@pytest.fixture
def harness_adapter():
    return _StubAdapter("openai_harness", AgentKind.SIMPLE_LLM, is_harness=True)


def test_true_harness_local_blocked_in_workflow(tmp_path, harness_adapter) -> None:
    svc = _make_service(tmp_path, harness_adapter, backend="local")
    repo = _make_repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide", "zero divisor")
    state = svc.run_task(task.id)
    types, graph = _audit_types(svc, state.run_id)
    assert "harness_execution_blocked" in types
    # the attempt was recorded but not executed -> failed with policy error
    attempts = graph["attempts"]
    assert attempts and any(
        "blocked_by_execution_policy" in (a.get("error") or "") for a in attempts)


def test_true_harness_local_override_audited(tmp_path, harness_adapter) -> None:
    svc = _make_service(tmp_path, harness_adapter, backend="local", allow_local_harness=True)
    repo = _make_repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide", "zero divisor")
    state = svc.run_task(task.id)
    types, _ = _audit_types(svc, state.run_id)
    assert "local_harness_override" in types
    assert "harness_execution_blocked" not in types


def test_true_harness_docker_allowed(tmp_path, harness_adapter) -> None:
    # backend=docker: policy allows the harness (no block, no override audit)
    svc = _make_service(tmp_path, harness_adapter, backend="docker")
    repo = _make_repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide", "zero divisor")
    state = svc.run_task(task.id)
    types, _ = _audit_types(svc, state.run_id)
    assert "harness_execution_blocked" not in types
    assert "local_harness_override" not in types


def test_simple_model_local_audited(tmp_path) -> None:
    adapter = _StubAdapter("claude", AgentKind.CLAUDE, is_harness=False)
    svc = _make_service(tmp_path, adapter, backend="local")
    repo = _make_repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide", "zero divisor")
    state = svc.run_task(task.id)
    types, _ = _audit_types(svc, state.run_id)
    assert "model_adapter_local" in types
    assert "harness_execution_blocked" not in types


def test_fake_patch_local_allowed(tmp_path) -> None:
    adapter = _StubAdapter("patch", AgentKind.PATCH, is_harness=False)
    svc = _make_service(tmp_path, adapter, backend="local")
    repo = _make_repo(svc, tmp_path)
    task = svc.create_task(repo.id, "Fix divide", "zero divisor")
    state = svc.run_task(task.id)
    types, _ = _audit_types(svc, state.run_id)
    assert "harness_execution_blocked" not in types
    assert "model_adapter_local" not in types
