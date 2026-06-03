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
from acp.schemas.provider_policy import ProviderPolicy
from acp.schemas.task import Task
from acp.schemas.workspace import DiffBundle
from acp.workspaces.base import Workspace

__all__ = ["HarnessTools", "OpenAIHarnessAdapter"]


def _is_timeout(exc: Exception) -> bool:
    """True for read/connect timeouts — these must NOT be retried (a retry would
    blow the wall-time budget); transient 429/5xx errors are retried instead."""
    name = type(exc).__name__.lower()
    return "timeout" in name or "timeout" in str(exc).lower()

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
                 max_steps: int = 8, max_tool_calls: int = 50,
                 max_nudges: int = 2, max_api_retries: int = 2,
                 call_timeout_s: float = 60.0) -> None:
        self.name = name
        self.model_name = model
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.max_nudges = max_nudges
        self.max_api_retries = max_api_retries
        self.call_timeout_s = call_timeout_s

    def provider_policy(self) -> ProviderPolicy:
        """The declared budget-safety contract this harness enforces (WS2)."""
        return ProviderPolicy(provider="openai", max_retries=0,
                              per_call_timeout_s=self.call_timeout_s,
                              retry_non_timeout_only=True, wall_budget_enforced=True)

    def _client(self):
        from acp.core.config import get_settings
        from acp.core.optional import try_import

        openai = try_import("openai")
        if openai is None:
            return None
        key = get_settings().openai_api_key
        if key is None:
            return None
        # No SDK retries: the default (2) multiplied each request's wall time via
        # exponential backoff (~600s past a 120s budget); even one retry doubles a
        # timed-out call (observed 241s vs a 120s budget). The harness drives its
        # own multi-step loop, so a per-call timeout (set per request, bounded by
        # the remaining wall budget) is the single, hard latency ceiling.
        return openai.OpenAI(api_key=key.get_secret_value(),
                             max_retries=self.provider_policy().max_retries)

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
        nudges = 0  # times we've re-prompted a prose-only (no tool call) response
        ledger = make_budget_ledger(budget, max_steps=self.max_steps,
                                    max_tool_calls=self.max_tool_calls, now=t0)
        try:
            while True:
                ledger.begin_step()
                error = ledger.violation(time.monotonic())
                if error:
                    break
                # Bound each request by the wall-time budget remaining (computed in
                # the retry loop below): without a per-call timeout the between-step
                # ledger check can't fire until a (possibly 10-min) call returns.
                # tool_choice="required" forces a tool call every turn (finish is
                # itself a tool, so the agent can still end). Observed live: without
                # it gpt-4o-mini often answers the task in prose and never calls
                # write_file, so the harness produced no edit. Required + the nudge
                # below (belt-and-suspenders) drive activation to ~100%.
                #
                # Our own bounded retry on transient (non-timeout) API errors: the
                # SDK's retries are disabled (they doubled wall time on timeouts), but
                # a 429/500 must not be miscounted as a capability failure that would
                # poison the capability matrix. Each retry re-derives the per-call
                # timeout from the remaining wall budget, so it stays budget-safe.
                # Observed live: infra hangs are always a hung FIRST call (~120s,
                # zero tool calls). Cap each request well under the wall budget so a
                # hang fails fast, and retry a *timeout* only when no tool has run yet
                # (a pure infra hang, safe to repeat). A timeout after real work is not
                # retried (would redo work) and becomes TIMED_OUT. Non-timeout 429/5xx
                # retry regardless. Each try re-derives remaining, so it's budget-safe.
                resp = None
                api_tries = 0
                while True:
                    remaining = budget.max_wall_time_s - (time.monotonic() - t0)
                    if remaining <= 0:
                        error = "budget_exceeded:wall"
                        break
                    per_call = min(remaining, self.call_timeout_s)
                    try:
                        resp = client.chat.completions.create(
                            model=self.model_name, messages=messages, tools=_TOOLS_SPEC,
                            tool_choice="required", timeout=max(5.0, per_call),
                        )
                        break
                    except Exception as api_exc:  # noqa: BLE001
                        is_to = _is_timeout(api_exc)
                        retryable = api_tries < self.max_api_retries and (
                            not is_to or not tools.tool_calls)
                        if not retryable:
                            raise
                        api_tries += 1
                if resp is None:
                    break
                usage = getattr(resp, "usage", None)
                if usage:
                    p = getattr(usage, "prompt_tokens", 0)
                    c = getattr(usage, "completion_tokens", 0)
                    in_tok += p
                    out_tok += c
                    ledger.charge_cost((p + c) / 1000 * cost_per_1k(self.model_name))
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    # Observed live: gpt-4o-mini sometimes answers in prose (e.g. a
                    # code block) instead of calling write_file, then we'd silently
                    # give up with no edit. If nothing has been written yet, nudge it
                    # to use the tools and retry a bounded number of times.
                    if not tools.files_written and nudges < self.max_nudges:
                        nudges += 1
                        messages.append({"role": "assistant", "content": msg.content or ""})
                        messages.append({"role": "user", "content": (
                            "Your reply made no tool call, so nothing changed. You MUST "
                            "use the tools (write_file to create/edit files, run_command "
                            "to run tests) to do the task — prose is ignored. Continue now."
                        )})
                        continue
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
            ledger=ledger, tool_choice_mode="required", tools_offered=len(_TOOLS_SPEC),
        )

    async def review(
        self, task: Task, diff: DiffBundle, context_pack: ContextPack, budget: Budget
    ) -> AgentReviewResult:
        return AgentReviewResult(verdict="uncertain", confidence=0.2)
