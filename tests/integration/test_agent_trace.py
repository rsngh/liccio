"""Normalized AgentTrace capture (round-3 R3-2)."""

from __future__ import annotations

import pytest
from git import Repo

from acp.agents.trace import build_agent_trace
from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.schemas.agent import AgentAttempt, AgentAttemptResult, DiffBundleRef, ToolCallRecord

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


def test_build_trace_from_harness_result() -> None:
    attempt = AgentAttempt(task_id="t", agent_kind="simple_llm", agent_name="openai_harness")
    result = AgentAttemptResult(
        status="succeeded",
        diff=DiffBundleRef(unified_diff="+a\n+b\n", changed_files=["m.py"]),
        input_token_count=100, output_token_count=50, estimated_cost_usd=0.001,
        tool_calls=[
            ToolCallRecord(tool_name="read_file", arguments={"path": "m.py"}),
            ToolCallRecord(tool_name="write_file", arguments={"path": "m.py"}),
            ToolCallRecord(tool_name="run_command", arguments={"command": ["pytest"]}),
        ],
        metadata={"session_id": "sess_1"},
    )
    tr = build_agent_trace(attempt, result, is_harness=True)
    assert tr.is_harness and tr.tool_calls == 3
    assert tr.file_reads == 1 and tr.file_writes == ["m.py"] and tr.commands == 1
    assert tr.session_id == "sess_1" and tr.input_tokens == 100


def test_build_trace_from_simple_adapter() -> None:
    attempt = AgentAttempt(task_id="t", agent_kind="patch", agent_name="patch")
    result = AgentAttemptResult(
        status="succeeded",
        diff=DiffBundleRef(unified_diff="+x\n", changed_files=["calc.py"]),
    )
    tr = build_agent_trace(attempt, result, is_harness=False)
    # no tool calls, but writes derived from the diff -> still comparable
    assert tr.tool_calls == 0
    assert tr.file_writes == ["calc.py"]
    assert tr.is_harness is False


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'tr.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def test_traces_persisted_in_run_graph(service, tmp_path) -> None:
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "test_calculator.py").write_text(
        "from calculator import divide\n\n\ndef test_divide():\n    assert divide(6, 2) == 3\n"
    )
    (src / "pyproject.toml").write_text(
        '[project]\nname = "tr"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "test_calculator.py", "pyproject.toml"])
    r.index.commit("init")
    repo = service.create_repo("tr", str(src), default_branch="master")
    task = service.create_task(repo.id, "Fix divide bug", "zero divisor",
                              metadata={"files": {"calculator.py": FIXED}})
    state = service.run_task(task.id)
    graph = AppService(service.settings).full_run_graph(state.run_id)
    assert graph["agent_traces"], "no agent traces persisted"
    assert all("adapter_name" in t for t in graph["agent_traces"])
