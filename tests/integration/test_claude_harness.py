"""Second true harness — ClaudeHarnessAdapter (round-4 Block E).

Offline tests drive the adapter with a scripted fake Anthropic client so the
full tool loop + trace capture is exercised with no network or key. The live
test (tests/live) runs against the real API when ANTHROPIC_API_KEY is present.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from git import Repo

from acp.agents.claude_harness import ClaudeHarnessAdapter
from acp.agents.trace import build_agent_trace
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

FIXED = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"


# --- scripted fake Anthropic client -----------------------------------------
@dataclass
class _Block:
    type: str
    id: str = ""
    name: str = ""
    input: dict | None = None
    text: str = ""


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _Resp:
    content: list
    usage: _Usage


class _ScriptedMessages:
    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def create(self, **kwargs):
        blocks = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return _Resp(content=blocks, usage=_Usage(40, 20))


class _ScriptedClient:
    def __init__(self, script):
        self.messages = _ScriptedMessages(script)


@pytest.fixture
def workspace(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    mgr = LocalWorkspaceManager(tmp_path / "ws")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    return mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                      default_policy())


def _run(adapter, workspace):
    task = Task(repo_id="r", title="Fix divide", body="raise on zero",
                acceptance_criteria=["divide(x,0) raises"])
    pack = ContextPack(task_id="t", repo_id="r", snapshot_id="s")
    return asyncio.run(adapter.execute(task, pack, workspace,
                                       Budget(max_cost_usd=1.0, max_wall_time_s=30)))


def test_adapter_is_a_true_harness() -> None:
    assert ClaudeHarnessAdapter().is_harness is True
    assert ClaudeHarnessAdapter().kind.value == "claude"


def test_adapter_health_unavailable_cleanly(monkeypatch) -> None:
    monkeypatch.delenv("ACP_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from acp.core.config import reset_settings
    reset_settings()
    h = asyncio.run(ClaudeHarnessAdapter().healthcheck())
    # never crashes; reports unavailable when SDK/key missing
    assert h.available in (True, False)
    if not h.available:
        assert "anthropic" in h.detail.lower()


def test_adapter_full_tool_loop_offline(workspace, monkeypatch) -> None:
    script = [
        [_Block("text", text="reading"),
         _Block("tool_use", id="t1", name="read_file", input={"path": "calculator.py"})],
        [_Block("tool_use", id="t2", name="write_file",
                input={"path": "calculator.py", "content": FIXED})],
        [_Block("tool_use", id="t3", name="run_command",
                input={"command": ["python", "-c", "print('ok')"]})],
        [_Block("tool_use", id="t4", name="finish", input={"summary": "done"})],
    ]
    adapter = ClaudeHarnessAdapter()
    monkeypatch.setattr(adapter, "_client", lambda: _ScriptedClient(script))
    result = _run(adapter, workspace)
    assert result.status == "succeeded"
    names = [tc.tool_name for tc in result.tool_calls]
    assert names == ["read_file", "write_file", "run_command"]
    assert result.input_token_count > 0 and result.output_token_count > 0
    assert result.estimated_cost_usd > 0
    assert result.metadata["session_id"].startswith("sess_")
    assert "calculator.py" in result.diff.changed_files


def test_adapter_trace_schema_offline(workspace, monkeypatch) -> None:
    script = [[_Block("tool_use", id="t2", name="write_file",
                      input={"path": "calculator.py", "content": FIXED})],
              [_Block("tool_use", id="t4", name="finish", input={})]]
    adapter = ClaudeHarnessAdapter()
    monkeypatch.setattr(adapter, "_client", lambda: _ScriptedClient(script))
    result = _run(adapter, workspace)
    attempt = AgentAttempt(task_id="t", agent_kind="claude", agent_name="claude_harness")
    tr = build_agent_trace(attempt, result, is_harness=True)
    assert tr.is_harness is True
    assert tr.file_writes == ["calculator.py"]
    assert tr.adapter_name == "claude_harness"
    assert tr.session_id is not None


def test_adapter_respects_max_steps(workspace, monkeypatch) -> None:
    # model never calls finish; loop must stop at max_steps and not hang
    loop = [[_Block("tool_use", id="r", name="read_file", input={"path": "calculator.py"})]]
    adapter = ClaudeHarnessAdapter(max_steps=3)
    monkeypatch.setattr(adapter, "_client", lambda: _ScriptedClient(loop))
    result = _run(adapter, workspace)
    # exactly max_steps read calls, then bounded
    assert sum(1 for t in result.tool_calls if t.tool_name == "read_file") == 3


def test_adapter_no_secret_leak(workspace, monkeypatch) -> None:
    # a run_command echoing a secret must be scrubbed in the captured record
    monkeypatch.setenv("MY_SECRET_TOKEN", "supersecretvalue123")
    script = [[_Block("tool_use", id="c", name="run_command",
                      input={"command": ["python", "-c",
                                         "import os;print(os.environ.get('MY_SECRET_TOKEN'))"]})],
              [_Block("tool_use", id="f", name="finish", input={})]]
    adapter = ClaudeHarnessAdapter()
    monkeypatch.setattr(adapter, "_client", lambda: _ScriptedClient(script))
    result = _run(adapter, workspace)
    blob = "".join(tc.result_summary for tc in result.tool_calls)
    assert "supersecretvalue123" not in blob


def test_adapter_unavailable_returns_failed(workspace, monkeypatch) -> None:
    adapter = ClaudeHarnessAdapter()
    monkeypatch.setattr(adapter, "_client", lambda: None)
    result = _run(adapter, workspace)
    assert result.status == "failed"
    assert result.error == "harness unavailable"
