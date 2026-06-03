"""Claude (Anthropic) tool-loop harness adapter (round-4 Block E).

The *second* true harness. Like :class:`OpenAIHarnessAdapter` it drives a real
agentic loop with workspace-scoped tools and captures the full normalized trace
(tool calls, file reads/writes, commands, diff, tokens, cost, wall time, session
id), with step/wall/cost budgets enforced. It shares the LLM-agnostic core in
``harness_base`` so its tool semantics and trace shape are identical to the
OpenAI harness — which is exactly what makes a multi-harness bakeoff a fair,
apples-to-apples comparison.

Distinct from the simple :class:`ClaudeAgentAdapter` (a one-shot JSON-edit model
adapter, ``is_harness=False``). This one is ``is_harness=True`` and requires the
Docker backend by default per the execution-backend policy.
"""

from __future__ import annotations

import time

from acp.agents.harness_base import (
    SYSTEM_PROMPT,
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

# Anthropic tool-use schema (input_schema rather than OpenAI's function wrapper).
_TOOLS_SPEC = [
    {"name": "read_file", "description": "Read a file in the workspace.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "Write/overwrite a file in the workspace.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["path", "content"]}},
    {"name": "run_command", "description": "Run a command (argv list) in the workspace.",
     "input_schema": {"type": "object", "properties": {
         "command": {"type": "array", "items": {"type": "string"}}},
         "required": ["command"]}},
    {"name": "finish", "description": "Signal the task is complete.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}},
]


class ClaudeHarnessAdapter:
    kind = AgentKind.CLAUDE
    is_harness = True  # second real tool-loop harness with trace capture

    def __init__(self, name: str = "claude_harness",
                 model: str = "claude-haiku-4-5", max_steps: int = 8,
                 max_tool_calls: int = 50) -> None:
        self.name = name
        self.model_name = model
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls

    def provider_policy(self) -> ProviderPolicy:
        """The declared budget-safety contract this harness enforces (WS2)."""
        return ProviderPolicy(provider="anthropic", max_retries=0,
                              per_call_timeout_s=60.0, retry_non_timeout_only=True,
                              wall_budget_enforced=True)

    def _client(self):
        from acp.core.config import get_settings
        from acp.core.optional import try_import

        anthropic = try_import("anthropic")
        if anthropic is None:
            return None
        key = get_settings().anthropic_api_key
        if key is None:
            return None
        # No SDK retries so backoff/retry can't multiply a single call past the
        # budget (see openai_harness: even one retry doubled a timed-out call).
        # The per-request timeout bounded by remaining wall budget is the hard cap.
        return anthropic.Anthropic(api_key=key.get_secret_value(),
                                   max_retries=self.provider_policy().max_retries)

    async def healthcheck(self) -> AgentHealth:
        client = self._client()
        return AgentHealth(
            name=self.name, kind=self.kind, available=client is not None,
            detail="ok" if client is not None
            else "anthropic SDK or ACP_ANTHROPIC_API_KEY missing",
        )

    async def plan(self, task, context_pack, workspace, budget) -> AgentPlan:
        return AgentPlan(summary=f"claude harness plan for {task.title}")

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
                # Bound each request by the remaining wall-time budget so a single
                # hung/rate-limited call can't run past it (parity with openai_harness).
                remaining = budget.max_wall_time_s - (time.monotonic() - t0)
                if remaining <= 0:
                    error = "budget_exceeded:wall"
                    break
                # tool_choice={"type": "any"} forces a tool call every turn (parity
                # with openai_harness; finish is itself a tool, so the agent can end).
                resp = client.messages.create(
                    model=self.model_name, max_tokens=2048, system=SYSTEM_PROMPT,
                    messages=messages, tools=_TOOLS_SPEC, tool_choice={"type": "any"},
                    timeout=max(5.0, remaining),
                )
                usage = getattr(resp, "usage", None)
                if usage:
                    p = getattr(usage, "input_tokens", 0)
                    c = getattr(usage, "output_tokens", 0)
                    in_tok += p
                    out_tok += c
                    ledger.charge_cost((p + c) / 1000 * cost_per_1k(self.model_name))
                blocks = list(resp.content)
                tool_uses = [b for b in blocks if getattr(b, "type", None) == "tool_use"]
                # Echo the assistant turn back so tool_result blocks can reference it.
                messages.append({
                    "role": "assistant",
                    "content": [_block_to_dict(b) for b in blocks],
                })
                if not tool_uses:
                    break
                ledger.add_tool_calls(len(tool_uses))
                results = []
                finished = False
                for tu in tool_uses:
                    result, done = dispatch_tool(tools, tu.name, dict(tu.input or {}))
                    finished = finished or done
                    results.append({"type": "tool_result", "tool_use_id": tu.id,
                                    "content": result})
                messages.append({"role": "user", "content": results})
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


def _block_to_dict(block) -> dict:
    """Normalize an Anthropic content block to a plain dict for message replay."""
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if btype == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name,
                "input": dict(block.input or {})}
    return {"type": btype or "text", "text": str(getattr(block, "text", ""))}
