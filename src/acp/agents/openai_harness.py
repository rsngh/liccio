"""OpenAI tool-loop harness adapter (round-2 Block I).

Unlike the simple JSON-edit model adapters, this is a real *harness*: the model
drives an agentic loop using tools (read_file / write_file / run_command /
finish), and the adapter captures the full trace — tool calls, file writes,
commands (each a mediated CommandRunRecord), diff, tokens, cost, wall time —
with budget/timeout/step limits. Commands are contained to the workspace and run
with secrets scrubbed.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from acp.core.enums import AgentKind, RunStatus
from acp.schemas.agent import (
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    Budget,
    DiffBundleRef,
    ToolCallRecord,
)
from acp.schemas.context import ContextPack
from acp.schemas.task import Task
from acp.schemas.workspace import CommandRunRecord, DiffBundle
from acp.workspaces.base import Workspace
from acp.workspaces.command_runner import CommandRunner
from acp.workspaces.diff import DiffCapturer

# rough $/1k tokens for gpt-4o-mini (input+output blended, conservative)
_COST_PER_1K = 0.0006


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


_TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file in the workspace.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write/overwrite a file in the workspace.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_command", "description": "Run a command (argv list) in the workspace.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "array", "items": {"type": "string"}}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "finish", "description": "Signal the task is complete.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}}}},
]


class OpenAIHarnessAdapter:
    kind = AgentKind.SIMPLE_LLM
    is_harness = True  # real tool-loop harness with trace capture

    def __init__(self, name: str = "openai_harness", model: str = "gpt-4o-mini",
                 max_steps: int = 8) -> None:
        self.name = name
        self.model_name = model
        self.max_steps = max_steps

    def _client(self):
        from acp.core.config import get_settings
        from acp.core.optional import try_import

        openai = try_import("openai")
        if openai is None:
            return None
        key = get_settings().openai_api_key
        if key is None:
            return None
        return openai.OpenAI(api_key=key.get_secret_value())

    async def healthcheck(self) -> AgentHealth:
        client = self._client()
        return AgentHealth(
            name=self.name, kind=self.kind, available=client is not None,
            detail="ok" if client is not None else "openai SDK or ACP_OPENAI_API_KEY missing",
        )

    async def plan(self, task, context_pack, workspace, budget) -> AgentPlan:
        return AgentPlan(summary=f"harness plan for {task.title}")

    async def execute(
        self, task: Task, context_pack: ContextPack, workspace: Workspace, budget: Budget
    ) -> AgentAttemptResult:
        t0 = time.monotonic()
        client = self._client()
        if client is None:
            return AgentAttemptResult(status=RunStatus.FAILED, error="harness unavailable",
                                      wall_time_s=time.monotonic() - t0)
        runner = CommandRunner(allowed_root=Path(workspace.path), scrub_secrets=True)
        tools = HarnessTools(workspace=workspace, runner=runner)
        session_id = f"sess_{int(t0 * 1000)}"
        messages: list[dict] = [
            {"role": "system", "content":
             "You are a coding agent operating in a sandboxed workspace. Use the tools "
             "to inspect and edit files and run commands. Make the minimal change to "
             "satisfy the task, then call finish."},
            {"role": "user", "content":
             f"Task: {task.title}\n{task.body}\n\nAcceptance: {task.acceptance_criteria}\n\n"
             f"Context:\n{context_pack.render_markdown()[:6000]}"},
        ]
        in_tok = out_tok = 0
        error = None
        try:
            for _ in range(self.max_steps):
                if time.monotonic() - t0 > budget.max_wall_time_s:
                    error = "timeout"
                    break
                cost = (in_tok + out_tok) / 1000 * _COST_PER_1K
                if cost > budget.max_cost_usd:
                    error = "budget_exceeded"
                    break
                resp = client.chat.completions.create(
                    model=self.model_name, messages=messages, tools=_TOOLS_SPEC,
                )
                usage = getattr(resp, "usage", None)
                if usage:
                    in_tok += getattr(usage, "prompt_tokens", 0)
                    out_tok += getattr(usage, "completion_tokens", 0)
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    break
                messages.append({"role": "assistant", "content": msg.content or "",
                                 "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
                finished = False
                for tc in msg.tool_calls:
                    fname = tc.function.name
                    fargs = json.loads(tc.function.arguments or "{}")
                    if fname == "finish":
                        finished = True
                        result = "ok"
                    elif fname == "read_file":
                        result = tools.read_file(fargs.get("path", ""))
                    elif fname == "write_file":
                        result = tools.write_file(fargs.get("path", ""), fargs.get("content", ""))
                    elif fname == "run_command":
                        result = tools.run_command(fargs.get("command", []))
                    else:
                        result = f"unknown tool {fname}"
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                if finished:
                    break
        except Exception as exc:  # noqa: BLE001 - structured failure
            error = str(exc)

        cap = DiffCapturer(str(workspace.path), workspace.spec.base_commit)
        status = RunStatus.SUCCEEDED if (tools.files_written and not error) else (
            RunStatus.TIMED_OUT if error == "timeout" else
            RunStatus.SUCCEEDED if tools.files_written else RunStatus.FAILED)
        return AgentAttemptResult(
            status=status,
            diff=DiffBundleRef(unified_diff=cap.get_unified_diff(),
                               changed_files=cap.get_changed_files()),
            input_token_count=in_tok, output_token_count=out_tok,
            estimated_cost_usd=round((in_tok + out_tok) / 1000 * _COST_PER_1K, 6),
            wall_time_s=time.monotonic() - t0,
            tool_calls=tools.tool_calls,
            error=error,
            metadata={"session_id": session_id, "steps_tool_calls": len(tools.tool_calls),
                      "commands": len(tools.command_runs), "files_written": tools.files_written},
        )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.2)
