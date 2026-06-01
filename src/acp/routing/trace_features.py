"""Trace-derived routing history features (round-5 WS7).

The bandit already learns a scalar reward per (context, action) arm. WS7 makes
the *evidence* behind that reward explicit: per (adapter, task_type) summaries
derived from normalized agent traces + outcomes, so routing can reason about an
agent's empirical success, cost, latency, human-review burden, and trace
complexity — not just an opaque reward.

These features are computed from a multi-harness bakeoff report (v1 or v2 cells)
and attached to ``PolicyObservation.trace_features`` during replay.
"""

from __future__ import annotations


def _task_type(cell: dict) -> str:
    return cell.get("task_type") or cell.get("task") or "unknown"


def cell_trace_features(cell: dict) -> dict:
    """Trace-derived features for a single bakeoff cell."""
    writes = cell.get("file_writes") or []
    return {
        "tool_calls": cell.get("tool_calls", 0),
        "commands": cell.get("commands", 0),
        "file_writes": len(writes) if isinstance(writes, list) else writes,
        "diff_lines": cell.get("diff_lines", 0),
        "cost_usd": cell.get("cost_usd", 0.0),
        "latency_s": cell.get("latency_s", 0.0),
        "is_harness": bool(cell.get("is_harness", False)),
        # a crude "how much work did it do" score
        "trace_complexity": (cell.get("tool_calls", 0) + cell.get("commands", 0)
                             + cell.get("diff_lines", 0) / 10.0),
    }


def summarize_agent_history(report: dict) -> dict:
    """Per (adapter, task_type) history features the router can consult.

    Returns ``{adapter: {task_type: {feature: value}}}`` with the WS7 feature
    family: success / cost / latency / human-review / post-merge-failure /
    trace-complexity / context-efficiency.
    """
    cells = report.get("cells", [])
    out: dict[str, dict[str, dict]] = {}
    adapters = sorted({c["adapter"] for c in cells})
    for adapter in adapters:
        per_type: dict[str, dict] = {}
        for tt in sorted({_task_type(c) for c in cells if c["adapter"] == adapter}):
            rows = [c for c in cells if c["adapter"] == adapter and _task_type(c) == tt]
            n = len(rows) or 1
            succ = sum(1 for r in rows if r.get("success"))
            tokens = sum(r.get("tokens", 0) for r in rows)
            per_type[tt] = {
                "agent_success_by_task_type": round(succ / n, 3),
                "agent_cost_by_task_type": round(sum(r.get("cost_usd", 0.0) for r in rows) / n, 6),
                "agent_latency_by_task_type": round(
                    sum(r.get("latency_s", 0.0) for r in rows) / n, 3),
                "agent_human_review_rate": round(
                    sum(1 for r in rows if r.get("human_review_required")) / n, 3),
                "agent_post_merge_failure_rate": round(
                    sum(1 for r in rows if r.get("post_merge_failure")) / n, 3),
                "agent_trace_complexity_score": round(
                    sum(cell_trace_features(r)["trace_complexity"] for r in rows) / n, 3),
                # successes per 1k tokens spent (higher = more context-efficient)
                "agent_context_efficiency": round(succ / (tokens / 1000.0), 3) if tokens else 0.0,
                "n": len(rows),
            }
        out[adapter] = per_type
    return out
