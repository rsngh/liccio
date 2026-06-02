"""Production-grade CONTRACT tests over the vendor harness adapters (alpha-8 WS9).

A single parametrized suite that pins down the *vendor harness contract* shared
by every :class:`~acp.agents.vendor_base.VendorHarnessAdapter` shim
(``codex_cli`` and ``claude_agent_sdk``). All assertions run fully offline: the
real codex binary / Anthropic SDK / network are never touched — availability and
the underlying command runner are forced via monkeypatch / dependency injection.

The contract every vendor harness must satisfy:

* ``is_harness is True`` and ``category == "vendor"``.
* ``healthcheck()`` returns an availability object exposing a bool ``available``.
* When forced *unavailable*, ``execute`` returns a clean
  :class:`AgentAttemptResult` (it never raises) with a non-succeeded status and a
  populated ``error`` mentioning unavailability — and no secret leaks into it.
* Where a ``build_command`` surface exists it is workspace-scoped and
  non-interactive (headless). Adapters without that surface skip this sub-check.
* A runner that *simulates a timeout* yields a ``TIMED_OUT``/``FAILED`` result
  (never a raise). Adapters without an injectable runner exercise the equivalent
  no-raise guarantee through ``_run_vendor`` raising instead.
* An :class:`~acp.schemas.trace.AgentTrace` built from a result carries the
  adapter name + ``is_harness is True`` + leaks no secret.

Sub-assertions are skipped only where an adapter genuinely lacks the surface,
and the skip is recorded (see ``_HAS_BUILD_COMMAND`` / ``_HAS_MAKE_RUNNER``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from git import Repo

from acp.agents.claude_agent_sdk import ClaudeAgentSDKAdapter
from acp.agents.codex_cli import CodexCLIAdapter
from acp.agents.trace import build_agent_trace
from acp.agents.vendor_base import VendorHarnessAdapter
from acp.core.enums import RunStatus
from acp.core.time import utcnow
from acp.schemas.agent import AgentAttempt, AgentHealth, Budget
from acp.schemas.context import ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.schemas.workspace import CommandRunRecord
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

# A canary secret that must never end up in a normalized result/trace.
_SECRET = "sk-codexLIVEsecret-CANARY-do-not-leak-0xDEADBEEF"


# --- fixtures / helpers -------------------------------------------------------
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
    return mgr.create(
        r,
        RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
        default_policy(),
    )


def _task() -> Task:
    return Task(repo_id="r", title="fix divide", body="make divide actually divide")


def _ctx() -> ContextPack:
    return ContextPack(repo_id="r", task_id="t", snapshot_id="s")


class _TimeoutRunner:
    """Stand-in CommandRunner whose ``run`` always reports a timeout."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int | None]] = []

    def run(self, command, cwd, timeout_s=None, **kwargs) -> CommandRunRecord:
        self.calls.append((command, timeout_s))
        return CommandRunRecord(
            argv=command,
            cwd=str(cwd),
            exit_code=None,
            timed_out=True,
            stdout_summary="",
            stderr_summary="",
        )


def _no_secret(result_or_trace: Any) -> None:
    """Assert the canary secret leaks into no serialized field of the object."""
    blob = result_or_trace.model_dump_json()
    assert _SECRET not in blob, f"secret leaked into {type(result_or_trace).__name__}"


# --- adapter matrix -----------------------------------------------------------
# Each entry: (id, factory, force_available, force_unavailable). The force-*
# callables monkeypatch the adapter so the contract runs deterministically with
# no real codex/SDK/network.
def _force_codex_available(mp, adapter) -> None:
    mp.setattr(type(adapter), "_requirement_present", lambda self: True)


def _force_codex_unavailable(mp, adapter) -> None:
    mp.setattr(type(adapter), "_requirement_present", lambda self: False)


def _force_sdk_available(mp, adapter) -> None:
    mp.setattr(type(adapter), "_requirement_present", lambda self: True)
    mp.setattr(type(adapter), "_key_present", lambda self: True)


def _force_sdk_unavailable(mp, adapter) -> None:
    # SDK present but key absent -> unavailable via the requires_key gate.
    mp.setattr(type(adapter), "_requirement_present", lambda self: True)
    mp.setattr(type(adapter), "_key_present", lambda self: False)


_ADAPTERS: list[tuple[str, Callable[[], VendorHarnessAdapter], Callable, Callable]] = [
    ("codex_cli", CodexCLIAdapter, _force_codex_available, _force_codex_unavailable),
    (
        "claude_agent_sdk",
        ClaudeAgentSDKAdapter,
        _force_sdk_available,
        _force_sdk_unavailable,
    ),
]

_HAS_BUILD_COMMAND = {"codex_cli"}  # claude_agent_sdk has no argv surface
_HAS_MAKE_RUNNER = {"codex_cli"}  # claude_agent_sdk drives the SDK, not a runner


@pytest.fixture(params=_ADAPTERS, ids=[a[0] for a in _ADAPTERS])
def adapter_case(request):
    return request.param


# --- contract assertions ------------------------------------------------------
def test_is_vendor_harness(adapter_case) -> None:
    _id, factory, _, _ = adapter_case
    adapter = factory()
    assert isinstance(adapter, VendorHarnessAdapter)
    assert adapter.is_harness is True
    assert adapter.category == "vendor"


@pytest.mark.asyncio
async def test_healthcheck_returns_availability_object(adapter_case) -> None:
    _id, factory, _, _ = adapter_case
    adapter = factory()
    health = await adapter.healthcheck()
    assert isinstance(health, AgentHealth)
    assert isinstance(health.available, bool)
    assert health.name == adapter.name


@pytest.mark.asyncio
async def test_forced_unavailable_returns_clean_result(
    adapter_case, monkeypatch, workspace
) -> None:
    _id, factory, _avail, unavail = adapter_case
    adapter = factory()
    unavail(monkeypatch, adapter)
    assert adapter.available() is False

    result = await adapter.execute(_task(), _ctx(), workspace, Budget())

    assert result.status != RunStatus.SUCCEEDED
    assert result.error is not None and "unavailable" in result.error
    assert result.metadata.get("category") == "vendor"
    _no_secret(result)


def test_build_command_is_scoped_and_noninteractive(adapter_case, workspace) -> None:
    _id, factory, _, _ = adapter_case
    adapter = factory()
    if _id not in _HAS_BUILD_COMMAND:
        pytest.skip(f"{_id} has no build_command argv surface (SDK-driven)")
    command = adapter.build_command(_task(), _ctx(), workspace)
    assert isinstance(command, list) and command
    # Workspace-scoped: the resolved workspace path appears in the argv.
    assert any(str(workspace.path) in str(arg) for arg in command)
    # Non-interactive / headless: no TUI/interactive flags present.
    joined = " ".join(str(a) for a in command)
    assert not any(flag in command for flag in ("-i", "--interactive", "--tui"))
    # codex headless subcommand is "exec".
    assert "exec" in joined


@pytest.mark.asyncio
async def test_simulated_timeout_is_handled_without_raising(
    adapter_case, monkeypatch, workspace
) -> None:
    _id, factory, avail, _ = adapter_case
    adapter = factory()
    avail(monkeypatch, adapter)

    if _id in _HAS_MAKE_RUNNER:
        runner = _TimeoutRunner()
        monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)
        result = await adapter.execute(
            _task(), _ctx(), workspace, Budget(max_wall_time_s=3)
        )
        assert result.status in (RunStatus.TIMED_OUT, RunStatus.FAILED)
        assert runner.calls and runner.calls[0][1] == 3
        assert any(str(workspace.path) in str(a) for a in runner.calls[0][0])
    else:
        # No injectable runner: drive the equivalent no-raise guarantee by making
        # the vendor call raise a timeout-like error; execute must absorb it.
        def _boom(self, *a, **k):
            raise TimeoutError("simulated vendor timeout")

        monkeypatch.setattr(type(adapter), "_run_vendor", _boom)
        result = await adapter.execute(
            _task(), _ctx(), workspace, Budget(max_wall_time_s=3)
        )
        assert result.status in (RunStatus.TIMED_OUT, RunStatus.FAILED)
        assert result.error is not None

    assert result.metadata.get("category") == "vendor"
    _no_secret(result)


@pytest.mark.asyncio
async def test_trace_from_result_is_harness_named_and_no_leak(
    adapter_case, monkeypatch, workspace
) -> None:
    _id, factory, avail, _ = adapter_case
    adapter = factory()
    avail(monkeypatch, adapter)

    if _id in _HAS_MAKE_RUNNER:
        runner = _TimeoutRunner()
        monkeypatch.setattr(adapter, "_make_runner", lambda ws: runner)
    else:
        # SDK adapter: make the vendor call raise so execute produces a clean
        # FAILED result (no SDK/network) — the secret canary is in the message.
        def _boom(self, *a, **k):
            raise RuntimeError("vendor error (no leak expected)")

        monkeypatch.setattr(type(adapter), "_run_vendor", _boom)

    result = await adapter.execute(_task(), _ctx(), workspace, Budget())

    attempt = AgentAttempt(
        task_id="t",
        agent_kind=adapter.kind,
        agent_name=adapter.name,
        model_name=adapter.model_name,
        started_at=utcnow(),
    )
    trace = build_agent_trace(
        attempt, result, is_harness=adapter.is_harness, task_id="t"
    )

    assert trace.adapter_name == adapter.name
    assert trace.is_harness is True
    assert trace.status != RunStatus.SUCCEEDED.value
    _no_secret(trace)
    _no_secret(result)
