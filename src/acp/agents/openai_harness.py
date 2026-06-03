"""OpenAI tool-loop harness adapter (round-2 Block I; refactored round-4 Block E).

Unlike the simple JSON-edit model adapters, this is a real *harness*: the model
drives an agentic loop using tools (read_file / write_file / run_command /
finish), and the adapter captures the full trace — tool calls, file writes,
commands (each a mediated CommandRunRecord), diff, tokens, cost, wall time —
with budget/timeout/step limits. Commands are contained to the workspace and run
with secrets scrubbed.

The LLM-agnostic core (tools, dispatch, result finalization) lives in
``harness_base`` and is shared with :class:`ClaudeHarnessAdapter`. ``HarnessTools``
is re-exported here for backwards compatibility with existing imports.
"""

from __future__ import annotations

import json
import time

from acp.agents.harness_base import (  # re-exported for back-compat
    SYSTEM_PROMPT,
    HarnessTools,
    cost_per_1k,
    dispatch_tool,
    finalize_result,
    make_budget_ledger,
    make_tools,
    user_prompt,
)
from acp.core.enums import AgentKind, RunStatus
from acp.schemas.agent import (
    AgentAttemptResult,
    AgentHealth,
    AgentPlan,
    AgentReviewResult,
    Budget,
)
from acp.schemas.context import ContextPack
from acp.schemas.task import Task
from acp.schemas.workspace import DiffBundle
from acp.workspaces.base import Workspace

__all__ = ["HarnessTools", "OpenAIHarnessAdapter"]

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
                 max_steps: int = 8, max_tool_calls: int = 50) -> None:
        self.name = name
        self.model_name = model
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls

    def _client(self):
        from acp.core.config import get_settings
        from acp.core.optional import try_import

        openai = try_import("openai")
        if openai is None:
            return None
        key = get_settings().openai_api_key
        if key is None:
            return None
        # Cap SDK retries: the default (2) multiplies each request's wall time via
        # exponential backoff, which let a single rate-limited call run ~600s past
        # the budget. One retry keeps transient resilience without budget blowout.
        return openai.OpenAI(api_key=key.get_secret_value(), max_retries=1)

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
        tools = make_tools(workspace)
        session_id = f"sess_{int(t0 * 1000)}"
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(task, context_pack)},
        ]
        in_tok = out_tok = 0
        error = None
        ledger = make_budget_ledger(budget, max_steps=self.max_steps,
                                    max_tool_calls=self.max_tool_calls, now=t0)
        try:
            while True:
                ledger.begin_step()
                error = ledger.violation(time.monotonic())
                if error:
                    break
                # Bound each request by the wall-time budget remaining: without a
                # per-call timeout the between-step ledger check can't fire until a
                # (possibly 10-min) call returns. Leave a small floor so near-budget
                # steps still get a real attempt rather than an instant timeout.
                remaining = budget.max_wall_time_s - (time.monotonic() - t0)
                if remaining <= 0:
                    error = "budget_exceeded:wall"
                    break
                resp = client.chat.completions.create(
                    model=self.model_name, messages=messages, tools=_TOOLS_SPEC,
                    timeout=max(5.0, remaining),
                )
                usage = getattr(resp, "usage", None)
                if usage:
                    p = getattr(usage, "prompt_tokens", 0)
                    c = getattr(usage, "completion_tokens", 0)
                    in_tok += p
                    out_tok += c
                    ledger.charge_cost((p + c) / 1000 * cost_per_1k(self.model_name))
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    break
                messages.append({"role": "assistant", "content": msg.content or "",
                                 "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
                ledger.add_tool_calls(len(msg.tool_calls))
                finished = False
                for tc in msg.tool_calls:
                    fargs = json.loads(tc.function.arguments or "{}")
                    result, done = dispatch_tool(tools, tc.function.name, fargs)
                    finished = finished or done
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                error = ledger.violation(time.monotonic())
                if finished or error:
                    break
        except Exception as exc:  # noqa: BLE001 - structured failure
            error = str(exc)

        return finalize_result(
            tools=tools, workspace=workspace, t0=t0, model=self.model_name,
            in_tok=in_tok, out_tok=out_tok, error=error, session_id=session_id,
            ledger=ledger,
        )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.2)
