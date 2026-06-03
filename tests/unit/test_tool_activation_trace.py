"""Tool activation metrics surface in AgentTrace (Alpha 11/12 WS4)."""

from __future__ import annotations

from acp.agents.trace import build_agent_trace
from acp.core.enums import AgentKind, RunStatus
from acp.schemas.agent import AgentAttempt, AgentAttemptResult, DiffBundleRef, ToolCallRecord


def _attempt():
    return AgentAttempt(task_id="t1", agent_kind=AgentKind.SIMPLE_LLM,
                        agent_name="openai_harness", model_name="gpt-4o-mini")


def test_prose_only_response_is_an_activation_failure() -> None:
    # tool_choice required but the model emitted no tool call -> activation failure
    # visible in the trace (the bug that masqueraded as model weakness).
    res = AgentAttemptResult(status=RunStatus.FAILED, error="no edit",
                             metadata={"tool_choice_mode": "required", "tools_offered": 4})
    tr = build_agent_trace(_attempt(), res, is_harness=True)
    assert tr.tools_required and tr.tools_offered == 4
    assert tr.tool_calls == 0
    assert tr.activation_failure_reason == "tools_required_but_none_called"


def test_valid_tool_calls_counted_and_no_activation_failure() -> None:
    res = AgentAttemptResult(
        status=RunStatus.SUCCEEDED,
        diff=DiffBundleRef(unified_diff="+x", changed_files=["a.py"]),
        tool_calls=[
            ToolCallRecord(tool_name="write_file", arguments={"path": "a.py"},
                           result_summary="ok"),
            ToolCallRecord(tool_name="run_command", arguments={"command": ["pytest"]},
                           result_summary="", error="boom"),
        ],
        metadata={"tool_choice_mode": "required", "tools_offered": 4})
    tr = build_agent_trace(_attempt(), res, is_harness=True)
    assert tr.tool_calls == 2 and tr.tool_calls_valid == 1  # one errored
    assert tr.first_tool_call_turn == 1
    assert tr.activation_failure_reason is None
