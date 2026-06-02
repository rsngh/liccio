"""Vendor coding-agent harness + capability registry tests (alpha-6 WS1).

Exercises the vendor harness category without any external SDK/CLI/key present
(as in this environment): the shims must report unavailable *gracefully* and
``execute`` must return a clean unavailable result rather than raising.
"""

from __future__ import annotations

import pytest
from git import Repo

from acp.agents.capabilities import build_capability_registry, classify
from acp.agents.claude_agent_sdk import ClaudeAgentSDKAdapter
from acp.agents.codex_cli import CodexCLIAdapter
from acp.agents.fake import FakeAgentAdapter
from acp.agents.openai_harness import OpenAIHarnessAdapter
from acp.agents.registry import AgentRegistry
from acp.agents.vendor_base import VendorHarnessAdapter
from acp.core.enums import RunStatus
from acp.schemas.agent import Budget
from acp.schemas.context import ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

VENDOR_SHIMS = [ClaudeAgentSDKAdapter, CodexCLIAdapter]


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


def _registry() -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(FakeAgentAdapter())
    reg.register(OpenAIHarnessAdapter())
    reg.register(ClaudeAgentSDKAdapter())
    reg.register(CodexCLIAdapter())
    return reg


@pytest.mark.parametrize("cls", VENDOR_SHIMS)
def test_vendor_adapter_marks_category_and_harness(cls) -> None:
    adapter = cls()
    assert adapter.category == "vendor"
    assert adapter.is_harness is True
    assert isinstance(adapter, VendorHarnessAdapter)
    assert classify(adapter) == "vendor"


@pytest.mark.parametrize("cls", VENDOR_SHIMS)
@pytest.mark.asyncio
async def test_vendor_shim_reports_availability_without_raising(cls) -> None:
    """Capability detection + healthcheck never raise; detail explains the state."""
    adapter = cls()
    available = adapter.available()  # must not raise
    health = await adapter.healthcheck()  # must not raise
    assert isinstance(available, bool)
    assert health.available is available
    assert health.detail  # always explains the state ("ok" or why-not)


def test_claude_agent_sdk_unavailable_without_key() -> None:
    """The SDK shim degrades cleanly when no Anthropic key is configured."""
    adapter = ClaudeAgentSDKAdapter()
    if adapter._key_present():
        pytest.skip("Anthropic key configured in this environment")
    assert adapter.available() is False
    assert "key" in adapter._unavailable_detail()


@pytest.mark.parametrize("cls", VENDOR_SHIMS)
@pytest.mark.asyncio
async def test_unavailable_execute_returns_clean_result(cls, workspace) -> None:
    """When unavailable, execute returns a clean failed result rather than raising."""
    adapter = cls()
    if adapter.available():
        pytest.skip(f"{adapter.name} is live in this environment")
    result = await adapter.execute(
        Task(repo_id="r", title="t", body="b"),
        ContextPack(repo_id="r", task_id="t", snapshot_id="s"),
        workspace, Budget(),
    )
    assert result.status == RunStatus.FAILED
    assert result.error is not None
    assert "unavailable" in result.error
    assert result.metadata.get("category") == "vendor"
    assert result.metadata.get("available") is False


@pytest.mark.asyncio
async def test_capability_registry_lists_categories_and_availability() -> None:
    caps = await build_capability_registry(_registry())
    # Every adapter appears with a category + availability.
    names = caps.names()
    assert {"fake", "openai_harness", "claude_agent_sdk", "codex_cli"} <= set(names)
    for entry in caps.entries:
        assert entry.category in {"deterministic", "simple_model", "acp_harness", "vendor"}
        assert isinstance(entry.available, bool)

    assert caps.get("fake").category == "deterministic"
    assert caps.get("openai_harness").category == "acp_harness"

    vendors = {e.name for e in caps.by_category("vendor")}
    assert vendors == {"claude_agent_sdk", "codex_cli"}
    for v in caps.by_category("vendor"):
        assert v.is_harness is True
        assert v.requirement  # records its SDK/CLI requirement
        assert isinstance(v.available, bool)  # live availability is reported
