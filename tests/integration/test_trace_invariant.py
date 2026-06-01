"""AgentTrace mandatory invariant (round-4 Block C).

Every AgentAttempt must carry exactly one normalized AgentTrace, even when the
adapter exposes no tool calls (the trace is synthesized from the diff). The
invariant holds end-to-end and survives a restart via the run graph.
"""

from __future__ import annotations

import pytest
from git import Repo

from acp.agents.trace import build_agent_trace
from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.schemas.agent import AgentAttempt, AgentAttemptResult, DiffBundleRef, ToolCallRecord

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'inv.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def _repo_and_task(service, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n")
    (src / "pyproject.toml").write_text(
        '[project]\nname = "inv"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n')
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    repo = service.create_repo("inv", str(src), default_branch="master")
    task = service.create_task(repo.id, "Fix divide bug", "zero divisor",
                               metadata={"files": {"calculator.py": FIXED}})
    return repo, task


def test_every_attempt_has_agent_trace(service, tmp_path) -> None:
    _, task = _repo_and_task(service, tmp_path)
    state = service.run_task(task.id)
    runner = service._runners[state.run_id]
    assert runner.artifacts.attempts, "no attempts ran"
    assert len(runner.artifacts.agent_traces) == len(runner.artifacts.attempts)
    attempt_ids = {a.id for a in runner.artifacts.attempts}
    trace_attempt_ids = {t.attempt_id for t in runner.artifacts.agent_traces}
    assert trace_attempt_ids == attempt_ids


def test_patch_agent_trace() -> None:
    attempt = AgentAttempt(task_id="t", agent_kind="patch", agent_name="patch")
    result = AgentAttemptResult(status="succeeded",
                                diff=DiffBundleRef(unified_diff="+x\n", changed_files=["c.py"]))
    tr = build_agent_trace(attempt, result, is_harness=False)
    assert tr.is_harness is False and tr.file_writes == ["c.py"] and tr.tool_calls == 0


def test_fake_agent_trace() -> None:
    attempt = AgentAttempt(task_id="t", agent_kind="fake", agent_name="fake")
    # a fake adapter that produced nothing still yields a (minimal) trace
    result = AgentAttemptResult(status="failed")
    tr = build_agent_trace(attempt, result, is_harness=False)
    assert tr.adapter_name == "fake" and tr.file_writes == [] and tr.changed_files == []


def test_simple_model_trace() -> None:
    attempt = AgentAttempt(task_id="t", agent_kind="claude", agent_name="claude")
    result = AgentAttemptResult(
        status="succeeded", input_token_count=80, output_token_count=20,
        diff=DiffBundleRef(unified_diff="+a\n+b\n", changed_files=["m.py"]))
    tr = build_agent_trace(attempt, result, is_harness=False)
    assert tr.is_harness is False and tr.file_writes == ["m.py"]
    assert tr.input_tokens == 80 and tr.diff_lines == 2


def test_openai_harness_trace() -> None:
    attempt = AgentAttempt(task_id="t", agent_kind="simple_llm", agent_name="openai_harness")
    result = AgentAttemptResult(
        status="succeeded", diff=DiffBundleRef(unified_diff="+x\n", changed_files=["m.py"]),
        tool_calls=[ToolCallRecord(tool_name="read_file", arguments={"path": "m.py"}),
                    ToolCallRecord(tool_name="write_file", arguments={"path": "m.py"})],
        metadata={"session_id": "s1"})
    tr = build_agent_trace(attempt, result, is_harness=True)
    assert tr.is_harness is True and tr.file_reads == 1 and tr.file_writes == ["m.py"]


def test_run_graph_includes_agent_traces_after_restart(service, tmp_path) -> None:
    _, task = _repo_and_task(service, tmp_path)
    state = service.run_task(task.id)
    # fresh service instance => everything must come from the DB
    graph = AppService(service.settings).full_run_graph(state.run_id)
    assert graph["agent_traces"], "no agent traces after restart"
    attempt_ids = {a["id"] for a in graph["attempts"]}
    traced = {t["attempt_id"] for t in graph["agent_traces"]}
    assert attempt_ids and attempt_ids.issubset(traced)
