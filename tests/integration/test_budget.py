"""Budget ledger + harness hard-stops (round-5 WS12)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from git import Repo

from acp.agents.claude_harness import ClaudeHarnessAdapter
from acp.core.budget import BudgetLedger, BudgetPolicy
from acp.schemas.agent import Budget
from acp.schemas.context import ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy


# --- BudgetLedger unit tests -------------------------------------------------
def test_ledger_charges_and_records_events() -> None:
    led = BudgetLedger(policy=BudgetPolicy(max_cost_usd=1.0))
    led.start(0.0)
    led.charge_cost(0.3)
    led.charge_cost(0.4)
    assert round(led.cost_usd, 3) == 0.7
    charges = [e for e in led.events if e.kind == "charge"]
    assert len(charges) == 2 and charges[-1].cumulative == pytest.approx(0.7)


def test_ledger_cost_violation() -> None:
    led = BudgetLedger(policy=BudgetPolicy(max_cost_usd=0.5))
    led.start(0.0)
    led.charge_cost(0.6)
    assert led.violation(now=1.0) == "budget_exceeded:cost"
    assert any(e.kind == "violation" and e.resource == "cost" for e in led.events)


def test_ledger_wall_violation() -> None:
    led = BudgetLedger(policy=BudgetPolicy(max_wall_time_s=10.0))
    led.start(0.0)
    assert led.violation(now=11.0) == "budget_exceeded:wall"


def test_ledger_steps_and_tool_calls_violation() -> None:
    led = BudgetLedger(policy=BudgetPolicy(max_steps=2, max_tool_calls=3))
    led.start(0.0)
    for _ in range(3):
        led.begin_step()
    assert led.violation(now=0.0) == "budget_exceeded:steps"
    led2 = BudgetLedger(policy=BudgetPolicy(max_tool_calls=3))
    led2.start(0.0)
    led2.add_tool_calls(5)
    assert led2.violation(now=0.0) == "budget_exceeded:tool_calls"


# --- scripted Claude client for harness hard-stop tests ----------------------
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


class _LoopClient:
    """Always returns one read tool_use (never finishes) with fixed token usage."""

    def __init__(self, tokens=10):
        self._tokens = tokens
        self.messages = self

    def create(self, **kw):
        return _Resp(
            content=[_Block("tool_use", id="r", name="read_file",
                            input={"path": "calculator.py"})],
            usage=_Usage(self._tokens, self._tokens))


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


def _run(adapter, workspace, budget):
    task = Task(repo_id="r", title="t", body="b", acceptance_criteria=["x"])
    pack = ContextPack(task_id="t", repo_id="r", snapshot_id="s")
    return asyncio.run(adapter.execute(task, pack, workspace, budget))


def test_harness_hard_stops_on_tool_calls(workspace, monkeypatch) -> None:
    adapter = ClaudeHarnessAdapter(max_steps=100, max_tool_calls=3)
    monkeypatch.setattr(adapter, "_client", lambda: _LoopClient())
    result = _run(adapter, workspace, Budget(max_cost_usd=99, max_wall_time_s=99))
    assert result.error == "budget_exceeded:tool_calls"
    # bounded trace: never wildly exceeds the cap
    assert result.metadata["budget"]["tool_calls"] <= 4
    assert "tool_calls" in result.metadata["budget"]["violations"]


def test_harness_hard_stops_on_cost(workspace, monkeypatch) -> None:
    # claude-haiku-4-5 ~ $0.002/1k tokens; 1000 tokens/call => $0.002/call
    adapter = ClaudeHarnessAdapter(max_steps=100, max_tool_calls=100)
    monkeypatch.setattr(adapter, "_client", lambda: _LoopClient(tokens=500))
    result = _run(adapter, workspace, Budget(max_cost_usd=0.003, max_wall_time_s=99))
    assert result.error == "budget_exceeded:cost"
    assert result.metadata["budget"]["cost_usd"] <= 0.01  # bounded


def test_harness_hard_stops_on_steps(workspace, monkeypatch) -> None:
    adapter = ClaudeHarnessAdapter(max_steps=4, max_tool_calls=100)
    monkeypatch.setattr(adapter, "_client", lambda: _LoopClient())
    result = _run(adapter, workspace, Budget(max_cost_usd=99, max_wall_time_s=99))
    assert result.error == "budget_exceeded:steps"
    # exactly max_steps model calls executed (read per step)
    reads = sum(1 for t in result.tool_calls if t.tool_name == "read_file")
    assert reads == 4
