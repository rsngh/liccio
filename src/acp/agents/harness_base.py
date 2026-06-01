"""Shared infrastructure for true tool-loop harnesses (round-4 Block E).

Both the OpenAI and Claude harnesses drive an agentic loop using the same
workspace-scoped tools (read_file / write_file / run_command / finish) and the
same trace capture. The LLM-agnostic pieces live here so a second (or third)
harness is a thin client over a shared, already-tested core:

* ``HarnessTools`` — workspace-contained, secret-scrubbed tool implementations
  that record every call as a ``ToolCallRecord`` (testable with no LLM).
* ``TOOL_NAMES`` / ``dispatch_tool`` — a single dispatch point so every harness
  executes tools identically.
* ``finalize_result`` — turns the captured state + diff into a normalized
  ``AgentAttemptResult`` with consistent status semantics across harnesses.

This keeps the harnesses comparable: identical tool semantics, identical trace
shape, identical status rules — only the model-call plumbing differs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from acp.core.enums import RunStatus
from acp.schemas.agent import AgentAttemptResult, DiffBundleRef, ToolCallRecord
from acp.schemas.workspace import CommandRunRecord
from acp.workspaces.base import Workspace
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.diff import DiffCapturer

# rough $/1k tokens, blended input+output, conservative per-model estimates
COST_PER_1K = {
    "gpt-4o-mini": 0.0006,
    "gpt-4o": 0.0075,
    "claude-haiku-4-5": 0.002,
    "claude-haiku-4-5-20251001": 0.002,
    "claude-sonnet-4-5": 0.009,
    "claude-sonnet-4-6": 0.009,
}
DEFAULT_COST_PER_1K = 0.002

TOOL_NAMES = ("read_file", "write_file", "run_command", "finish")

# System prompt shared by every harness so behaviour is comparable across them.
SYSTEM_PROMPT = (
    "You are a coding agent operating in a sandboxed workspace. Use the tools to "
    "inspect and edit files and run commands. Make the minimal change to satisfy "
    "the task, then call finish. Never print secrets or environment variables."
)


def cost_per_1k(model: str) -> float:
    return COST_PER_1K.get(model, DEFAULT_COST_PER_1K)


def user_prompt(task, context_pack) -> str:
    return (
        f"Task: {task.title}\n{task.body}\n\n"
        f"Acceptance: {task.acceptance_criteria}\n\n"
        f"Context:\n{context_pack.render_markdown()[:6000]}"
    )


@dataclass
class HarnessTools:
    """Workspace-scoped tools with full capture. Testable without an LLM."""

    workspace: Workspace
    runner: CommandRunner
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    command_runs: list[CommandRunRecord] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)

    @property
    def root(self) -> Path:
        return Path(self.workspace.path).resolve()

    def _safe(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError(f"path escapes workspace: {rel}")
        return p

    def _record(self, name: str, args: dict, summary: str, error: str | None = None) -> None:
        self.tool_calls.append(ToolCallRecord(
            tool_name=name, arguments=args, result_summary=summary[:2000], error=error,
        ))

    def read_file(self, path: str) -> str:
        try:
            content = self._safe(path).read_text(encoding="utf-8", errors="replace")
            self._record("read_file", {"path": path}, f"read {len(content)} chars")
            return content
        except Exception as exc:  # noqa: BLE001
            self._record("read_file", {"path": path}, "", error=str(exc))
            return f"ERROR: {exc}"

    def write_file(self, path: str, content: str) -> str:
        try:
            target = self._safe(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            self.files_written.append(path)
            self._record("write_file", {"path": path}, f"wrote {len(content)} chars")
            return "ok"
        except Exception as exc:  # noqa: BLE001
            self._record("write_file", {"path": path}, "", error=str(exc))
            return f"ERROR: {exc}"

    def run_command(self, command: list[str], timeout_s: int = 60) -> str:
        rec = self.runner.run(command, cwd=self.root, timeout_s=timeout_s)
        self.command_runs.append(rec)
        summary = f"exit={rec.exit_code}\n{rec.stdout_summary[:1500]}"
        self._record("run_command", {"command": command}, summary)
        return summary


def dispatch_tool(tools: HarnessTools, name: str, args: dict) -> tuple[str, bool]:
    """Execute one tool call. Returns (result_text, finished)."""
    if name == "finish":
        return "ok", True
    if name == "read_file":
        return tools.read_file(args.get("path", "")), False
    if name == "write_file":
        return tools.write_file(args.get("path", ""), args.get("content", "")), False
    if name == "run_command":
        return tools.run_command(args.get("command", [])), False
    return f"unknown tool {name}", False


def make_tools(workspace: Workspace) -> HarnessTools:
    runner = CommandRunner(allowed_root=Path(workspace.path), scrub_secrets=True)
    return HarnessTools(workspace=workspace, runner=runner)


def finalize_result(
    *, tools: HarnessTools, workspace: Workspace, t0: float, model: str,
    in_tok: int, out_tok: int, error: str | None, session_id: str,
) -> AgentAttemptResult:
    """Normalized result so every harness produces an identical trace shape."""
    cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
    if error == "timeout":
        status = RunStatus.TIMED_OUT
    elif tools.files_written:
        # A file write means the agent produced a candidate change; a non-fatal
        # error (e.g. a late budget cap) does not discard already-written work.
        status = RunStatus.SUCCEEDED
    else:
        status = RunStatus.FAILED
    return AgentAttemptResult(
        status=status,
        diff=DiffBundleRef(unified_diff=cap.get_unified_diff(),
                           changed_files=cap.get_changed_files()),
        input_token_count=in_tok, output_token_count=out_tok,
        estimated_cost_usd=round((in_tok + out_tok) / 1000 * cost_per_1k(model), 6),
        wall_time_s=time.monotonic() - t0,
        tool_calls=tools.tool_calls,
        error=error,
        metadata={"session_id": session_id, "steps_tool_calls": len(tools.tool_calls),
                  "commands": len(tools.command_runs), "files_written": tools.files_written},
    )
