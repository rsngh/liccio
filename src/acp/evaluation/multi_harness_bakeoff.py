"""Multi-harness no-patch bakeoff (round-4 Block F).

Runs a matrix of (no-patch task × adapter) and compares the normalized agent
traces + objective outcomes. NO task may carry a ``metadata["files"]`` patch —
every adapter must actually do the work — which is what turns the bakeoff from
"can solve" into "which agent solves it, how, and at what cost".

Each cell runs in its own AppService/registry on a fresh copy of the repo so
adapters never interfere. Per cell we record: success, verification pass,
reward, tool calls, commands, file writes, tokens, cost, latency, whether human
review was required, and a failure class. The whole report persists as an
EvalRun via :meth:`AppService.run_multi_harness_bakeoff`.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from acp.evaluation.trace_bakeoff import make_bug_repo


@dataclass
class NoPatchTask:
    key: str
    title: str
    body: str
    acceptance: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# Five no-patch task classes. They share the calculator bug repo (so scripted /
# fake adapters in tests behave deterministically) but differ in framing so the
# task classifier assigns different types/risk — enough to exercise the matrix.
NO_PATCH_TASKS: list[NoPatchTask] = [
    NoPatchTask("bugfix", "Fix divide by zero",
                "divide() returns 0 on a zero divisor; it must raise ZeroDivisionError.",
                ["divide(x, 0) raises ZeroDivisionError"]),
    NoPatchTask("test_generation", "Add a regression test",
                "Add a test that pins divide()'s zero-divisor behaviour.",
                ["a test covers the zero-divisor case"]),
    NoPatchTask("feature", "Add safe_divide helper",
                "Add a safe_divide(a, b, default) that returns default on zero divisor.",
                ["safe_divide returns the default on zero divisor"]),
    NoPatchTask("refactor", "Clarify divide implementation",
                "Refactor divide() for clarity without changing behaviour.",
                ["behaviour is unchanged"]),
    NoPatchTask("security", "Harden divide against bad input",
                "Validate inputs to divide() and reject untrusted/eval-style input safely.",
                ["no unsafe evaluation of inputs"]),
]


def _classify_failure(status: str, attempts: int, blocked: bool) -> str:
    if status == "succeeded":
        return "none"
    if blocked:
        return "blocked_by_policy"
    if status == "waiting_for_human":
        return "escalated_human_review"
    if attempts == 0:
        return "no_agent_selected"
    if status == "timed_out":
        return "agent_timeout"
    return "verification_or_agent_failure"


def run_multi_harness_bakeoff(
    adapter_factories: dict[str, Callable[[], object]],
    tasks: list[NoPatchTask] | None = None,
) -> dict:
    """Run every task through every adapter; return a comparison report.

    ``adapter_factories`` maps adapter name -> zero-arg factory (so each cell
    gets a fresh adapter instance). Raises ValueError if any task tries to
    smuggle in a pre-supplied patch.
    """
    from acp.agents.registry import AgentRegistry
    from acp.api.service import AppService
    from acp.core.config import ACPSettings

    task_list = tasks or NO_PATCH_TASKS
    for tk in task_list:
        if "files" in tk.metadata:
            raise ValueError(
                f"no-patch bakeoff task {tk.key!r} must not contain metadata['files'] "
                "(the agent must solve it, not apply a supplied patch)")
    cells: list[dict] = []
    taxonomy: dict[str, int] = {}
    for tk in task_list:
        for name, factory in adapter_factories.items():
            tmp = Path(tempfile.mkdtemp(prefix="acp_mhb_"))
            reg = AgentRegistry()
            reg.register(factory())  # type: ignore[arg-type]
            svc = AppService(ACPSettings(
                database_url=f"sqlite+aiosqlite:///{tmp / 'mhb.db'}",
                artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
                allow_local_harness=True,  # bakeoff runs harnesses locally on purpose
            ), registry=reg)
            make_bug_repo(tmp / "repo")
            repo = svc.create_repo("mhb", str(tmp / "repo"), default_branch="master")
            task = svc.create_task(repo.id, tk.title, tk.body,
                                   acceptance_criteria=tk.acceptance, metadata=dict(tk.metadata))
            state = svc.run_task(task.id)
            cells.append(_cell(svc, state, tk, name))
            fclass = cells[-1]["failure_class"]
            taxonomy[fclass] = taxonomy.get(fclass, 0) + 1

    return {
        "mode": "multi_harness_no_patch",
        "adapters": sorted(adapter_factories),
        "tasks": [t.key for t in task_list],
        "cells": cells,
        "comparison": _comparison(cells, sorted(adapter_factories)),
        "failure_taxonomy": taxonomy,
        "summary": {
            "n_cells": len(cells),
            "solved": sum(1 for c in cells if c["success"]),
            "solve_rate": round(sum(1 for c in cells if c["success"]) / max(1, len(cells)), 3),
        },
    }


def _cell(svc, state, task: NoPatchTask, adapter: str) -> dict:
    status = state.status if isinstance(state.status, str) else state.status.value
    runner = svc._runners.get(state.run_id)
    arts = runner.artifacts if runner else None
    traces = getattr(arts, "agent_traces", []) if arts else []
    tr = next((t for t in traces if t.attempt_id == state.selected_attempt_id),
              traces[0] if traces else None)
    verdict = arts.verdicts.get(state.selected_attempt_id) if arts and state.selected_attempt_id \
        else None
    reward = arts.reward.reward if arts and arts.reward else None
    review_required = bool(arts.review_item) if arts else False
    evaluation = arts.evaluation if arts else None
    blocked = any("blocked_by_execution_policy" in (a.error or "")
                  for a in (arts.attempts if arts else []))
    return {
        "name": f"{task.key}/{adapter}",
        "task": task.key,
        "adapter": adapter,
        "status": status,
        "success": status == "succeeded",
        "verification_pass": bool(verdict.passed) if verdict else False,
        "reward": round(reward, 4) if reward is not None else None,
        "tool_calls": tr.tool_calls if tr else 0,
        "commands": tr.commands if tr else 0,
        "file_writes": tr.file_writes if tr else [],
        "is_harness": tr.is_harness if tr else False,
        "tokens": (tr.input_tokens + tr.output_tokens) if tr else 0,
        "cost_usd": tr.estimated_cost_usd if tr else 0.0,
        "latency_s": round(tr.wall_time_s, 3) if tr else 0.0,
        "human_review_required": review_required,
        "security_risk": round(evaluation.security_risk, 3) if evaluation else None,
        "failure_class": _classify_failure(status, len(state.attempt_ids), blocked),
    }


def _comparison(cells: list[dict], adapters: list[str]) -> dict:
    """Per-adapter aggregate metrics — the apples-to-apples comparison."""
    out: dict[str, dict] = {}
    for a in adapters:
        rows = [c for c in cells if c["adapter"] == a]
        n = len(rows) or 1
        solved = [c for c in rows if c["success"]]
        out[a] = {
            "cells": len(rows),
            "solve_rate": round(len(solved) / n, 3),
            "mean_tool_calls": round(sum(c["tool_calls"] for c in rows) / n, 2),
            "mean_cost_usd": round(sum(c["cost_usd"] for c in rows) / n, 6),
            "mean_latency_s": round(sum(c["latency_s"] for c in rows) / n, 3),
            "total_tokens": sum(c["tokens"] for c in rows),
            "is_harness": any(c["is_harness"] for c in rows),
        }
    return out


def bakeoff_to_markdown(report: dict) -> str:
    lines = ["# Multi-harness no-patch bakeoff", "",
             f"- cells: {report['summary']['n_cells']}",
             f"- solve rate: {report['summary']['solve_rate']}",
             f"- failure taxonomy: {report['failure_taxonomy']}", "",
             "| adapter | solve_rate | mean_tool_calls | mean_cost | harness |",
             "| --- | --- | --- | --- | --- |"]
    for a, m in report["comparison"].items():
        lines.append(f"| {a} | {m['solve_rate']} | {m['mean_tool_calls']} | "
                     f"{m['mean_cost_usd']} | {m['is_harness']} |")
    return "\n".join(lines) + "\n"
