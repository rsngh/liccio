"""Multi-harness bakeoff engine v2 (round-5 WS6).

Dataset-driven, with repetitions and rich per-task/per-adapter/per-run metrics
plus aggregates by adapter, task type, and risk. Each cell runs in its own
AppService/registry on a fresh fixture repo so adapters never interfere.

Unlike v1 (single calculator repo, fixed tasks), v2 reads the no-patch dataset,
builds the right fixture per task, repeats runs for stability, and reports a
comparison a reviewer can use to answer "which harness is best for which task
type, and at what cost".
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from git import Repo

from acp.evaluation.dataset import DatasetTask, load_dataset
from acp.evaluation.fixtures import build_fixture


def factory_for(name: str) -> Callable[[], object]:
    """Resolve an adapter name to a zero-arg factory for the bakeoff matrix."""
    if name == "openai_harness":
        from acp.agents.openai_harness import OpenAIHarnessAdapter
        return lambda: OpenAIHarnessAdapter(max_steps=6)
    if name == "claude_harness":
        from acp.agents.claude_harness import ClaudeHarnessAdapter
        return lambda: ClaudeHarnessAdapter(max_steps=6)
    if name == "patch":
        from acp.agents.patch_agent import PatchAgentAdapter
        return PatchAgentAdapter
    if name == "fake":
        from acp.agents.fake import FakeAgentAdapter
        return FakeAgentAdapter
    raise KeyError(f"unknown adapter {name!r} for bakeoff")


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


def _build_repo(svc, task: DatasetTask, root: Path):
    build_fixture(task.fixture, root)
    repo = Repo.init(root)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add("*")
    repo.index.commit("init")
    return svc.create_repo(task.key, str(root), default_branch="master")


def _cell(svc, state, task: DatasetTask, adapter: str, rep: int) -> dict:
    status = state.status if isinstance(state.status, str) else state.status.value
    runner = svc._runners.get(state.run_id)
    arts = runner.artifacts if runner else None
    traces = getattr(arts, "agent_traces", []) if arts else []
    tr = next((t for t in traces if t.attempt_id == state.selected_attempt_id),
              traces[0] if traces else None)
    verdict = (arts.verdicts.get(state.selected_attempt_id)
               if arts and state.selected_attempt_id else None)
    reward = arts.reward.reward if arts and arts.reward else None
    evaluation = arts.evaluation if arts else None
    blocked = any("blocked_by_execution_policy" in (a.error or "")
                  for a in (arts.attempts if arts else []))
    return {
        "name": f"{task.key}/{adapter}/r{rep}",
        "task": task.key, "task_type": task.task_type, "risk": task.risk,
        "adapter": adapter, "rep": rep, "status": status,
        "success": status == "succeeded",
        "verification_pass": bool(verdict.passed) if verdict else False,
        "reward": round(reward, 4) if reward is not None else None,
        "human_review_required": bool(arts.review_item) if arts else False,
        "tool_calls": tr.tool_calls if tr else 0,
        "commands": tr.commands if tr else 0,
        "file_reads": tr.file_reads if tr else 0,
        "file_writes": tr.file_writes if tr else [],
        "changed_files": tr.changed_files if tr else [],
        "diff_lines": tr.diff_lines if tr else 0,
        "tokens": (tr.input_tokens + tr.output_tokens) if tr else 0,
        "cost_usd": tr.estimated_cost_usd if tr else 0.0,
        "latency_s": round(tr.wall_time_s, 3) if tr else 0.0,
        "is_harness": tr.is_harness if tr else False,
        "security_risk": round(evaluation.security_risk, 3) if evaluation else None,
        "failure_class": _classify_failure(status, len(state.attempt_ids), blocked),
    }


def run_bakeoff_v2(
    adapter_factories: dict[str, Callable[[], object]],
    dataset_path: str | Path,
    *, repetitions: int = 1, backend: str = "local",
) -> dict:
    from acp.agents.registry import AgentRegistry
    from acp.api.service import AppService
    from acp.core.config import ACPSettings

    tasks = load_dataset(dataset_path)
    cells: list[dict] = []
    for task in tasks:
        for name, factory in adapter_factories.items():
            for rep in range(repetitions):
                tmp = Path(tempfile.mkdtemp(prefix="acp_v2_"))
                reg = AgentRegistry()
                reg.register(factory())  # type: ignore[arg-type]
                svc = AppService(ACPSettings(
                    database_url=f"sqlite+aiosqlite:///{tmp / 'v2.db'}",
                    artifact_dir=tmp / "art", workspace_dir=tmp / "ws",
                    workspace_backend=backend, allow_local_harness=True,
                ), registry=reg)
                repo = _build_repo(svc, task, tmp / "repo")
                t = svc.create_task(repo.id, task.title, task.body,
                                    acceptance_criteria=task.acceptance,
                                    metadata={})
                state = svc.run_task(t.id)
                cells.append(_cell(svc, state, task, name, rep))

    return {
        "mode": "multi_harness_v2",
        "backend": backend,
        "repetitions": repetitions,
        "adapters": sorted(adapter_factories),
        "dataset": str(dataset_path),
        "n_tasks": len(tasks),
        "cells": cells,
        "by_adapter": _aggregate(cells, "adapter"),
        "by_task_type": _aggregate(cells, "task_type"),
        "by_risk": _aggregate(cells, "risk"),
        "summary": {
            "n_cells": len(cells),
            "solve_rate": round(sum(c["success"] for c in cells) / max(1, len(cells)), 3),
        },
    }


def _aggregate(cells: list[dict], key: str) -> dict:
    out: dict[str, dict] = {}
    for val in sorted({c[key] for c in cells}):
        rows = [c for c in cells if c[key] == val]
        n = len(rows) or 1
        out[val] = {
            "cells": len(rows),
            "solve_rate": round(sum(r["success"] for r in rows) / n, 3),
            "verification_pass_rate": round(sum(r["verification_pass"] for r in rows) / n, 3),
            "human_review_rate": round(sum(r["human_review_required"] for r in rows) / n, 3),
            "mean_tool_calls": round(sum(r["tool_calls"] for r in rows) / n, 2),
            "mean_cost_usd": round(sum(r["cost_usd"] for r in rows) / n, 6),
            "mean_latency_s": round(sum(r["latency_s"] for r in rows) / n, 3),
            "total_tokens": sum(r["tokens"] for r in rows),
        }
    return out


def bakeoff_v2_to_markdown(report: dict) -> str:
    lines = ["# Multi-harness bakeoff v2", "",
             f"- backend: {report['backend']} | repetitions: {report['repetitions']}",
             f"- tasks: {report['n_tasks']} | cells: {report['summary']['n_cells']}",
             f"- solve rate: {report['summary']['solve_rate']}", "",
             "## By adapter", "",
             "| adapter | solve_rate | verif | human_review | tool_calls | cost |",
             "| --- | --- | --- | --- | --- | --- |"]
    for a, m in report["by_adapter"].items():
        lines.append(f"| {a} | {m['solve_rate']} | {m['verification_pass_rate']} | "
                     f"{m['human_review_rate']} | {m['mean_tool_calls']} | {m['mean_cost_usd']} |")
    lines += ["", "## By task type", "",
              "| task_type | solve_rate | human_review |", "| --- | --- | --- |"]
    for t, m in report["by_task_type"].items():
        lines.append(f"| {t} | {m['solve_rate']} | {m['human_review_rate']} |")
    return "\n".join(lines) + "\n"
