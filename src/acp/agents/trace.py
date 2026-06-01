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
        changed_files=changed,
        diff_lines=diff_lines,
        input_tokens=result.input_token_count,
        output_tokens=result.output_token_count,
        estimated_cost_usd=result.estimated_cost_usd,
        wall_time_s=result.wall_time_s,
        error=result.error,
    )
