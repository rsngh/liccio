"""Normalize any adapter's execution into a comparable AgentTrace (round-3 R3-2)."""

from __future__ import annotations

from acp.schemas.agent import AgentAttempt, AgentAttemptResult
from acp.schemas.trace import AgentTrace


def build_agent_trace(
    attempt: AgentAttempt, result: AgentAttemptResult, *, is_harness: bool = False,
    task_id: str | None = None,
) -> AgentTrace:
    tcs = result.tool_calls or []
    reads = sum(1 for t in tcs if t.tool_name == "read_file")
    writes = [t.arguments.get("path", "") for t in tcs if t.tool_name == "write_file"]
    commands = sum(1 for t in tcs if t.tool_name == "run_command")
    changed = list(result.diff.changed_files) if result.diff else []
    # Simple model adapters expose no tool calls; their "writes" are the changed
    # files from the diff, so the trace is still comparable.
    if not writes and changed:
        writes = changed
    diff_lines = len((result.diff.unified_diff or "").splitlines()) if result.diff else 0
    status = result.status if isinstance(result.status, str) else result.status.value

    # Tool activation signals (WS4). The harness reports its tool_choice mode and
    # offered-tool count via metadata; valid calls are those that ran error-free.
    # The tool_choice="required" bug shows here as required + tool_calls=0.
    meta = result.metadata or {}
    tool_choice_mode = meta.get("tool_choice_mode")
    tools_offered = int(meta.get("tools_offered", 0) or 0)
    tools_required = tool_choice_mode == "required"
    valid = sum(1 for t in tcs if not t.error)
    activation_failure_reason: str | None = None
    if is_harness and not tcs:
        activation_failure_reason = (
            "tools_required_but_none_called" if tools_required else "no_tool_calls")
    return AgentTrace(
        attempt_id=attempt.id,
        task_id=task_id or attempt.task_id,
        adapter_name=attempt.agent_name,
        is_harness=is_harness,
        model_name=attempt.model_name,
        session_id=str(result.metadata.get("session_id")) if result.metadata else None,
        status=status,
        tool_calls=len(tcs),
        file_reads=reads,
        file_writes=writes,
        commands=commands,
        tools_offered=tools_offered,
        tools_required=tools_required,
        tool_choice_mode=tool_choice_mode,
        tool_calls_valid=valid,
        first_tool_call_turn=1 if tcs else None,
        activation_failure_reason=activation_failure_reason,
        changed_files=changed,
        diff_lines=diff_lines,
        input_tokens=result.input_token_count,
        output_tokens=result.output_token_count,
        estimated_cost_usd=result.estimated_cost_usd,
        wall_time_s=result.wall_time_s,
        error=result.error,
    )
