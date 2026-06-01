"""Bakeoff matrix harness (round-1 two-day D2B4).

Runs a matrix of (task class × context strategy × verification policy × seed)
through the live workflow and produces a machine-readable scorecard with metrics
and a failure taxonomy. Real adapters are recorded as available/unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FIXED_CALC = (
    "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"
)

DEFAULT_TASKS = [
    ("bugfix", "Fix divide bug", "divide returns 0 on zero divisor"),
    ("feature", "Add subtract", "implement subtract function"),
    ("docs", "Update README", "improve docs in README.md"),
]
DEFAULT_STRATEGIES = ["minimal", "bug_reproduction", "hybrid_keyword_embedding"]
DEFAULT_VERIFICATION = ["standard", "strict"]


@dataclass
class BakeoffConfig:
    tasks: list[tuple[str, str, str]] = field(default_factory=lambda: list(DEFAULT_TASKS))
    strategies: list[str] = field(default_factory=lambda: list(DEFAULT_STRATEGIES))
    verification_policies: list[str] = field(default_factory=lambda: list(DEFAULT_VERIFICATION))
    seeds: list[int] = field(default_factory=lambda: [1, 2, 3])


def _classify_failure(status: str, attempts: int) -> str:
    if status == "succeeded":
        return "none"
    if status == "waiting_for_human":
        return "escalated_human_review"
    if status == "failed" and attempts == 0:
        return "no_agent"
    return "verification_or_agent_failure"


def run_bakeoff(service, repo_id: str, config: BakeoffConfig | None = None) -> dict:
    cfg = config or BakeoffConfig()
    available = []
    import asyncio

    try:
        available = asyncio.run(service.registry.available())
    except Exception:  # noqa: BLE001
        available = service.registry.names()

    cells: list[dict] = []
    taxonomy: dict[str, int] = {}
    agents_used: set[str] = set()
    rewards: list[float] = []
    latency_total = 0.0
    succeeded = 0
    human_reviews = 0
    for cls_name, title, body in cfg.tasks:
        for strat in cfg.strategies:
            for vpol in cfg.verification_policies:
                for seed in cfg.seeds:
                    task = service.create_task(
                        repo_id, title=f"{title} [{strat}/{vpol}/s{seed}]", body=body,
                        metadata={"files": {"calculator.py": FIXED_CALC},
                                  "context_strategy": strat, "seed": seed},
                    )
                    state = service.run_task(task.id)
                    status = state.status if isinstance(state.status, str) else state.status.value
                    runner = service._runners.get(state.run_id)
                    arts = runner.artifacts if runner else None
                    cost = sum(a.estimated_cost_usd for a in arts.attempts) if arts else 0.0
                    latency = sum(a.wall_time_s for a in arts.attempts) if arts else 0.0
                    tokens = sum(a.total_token_count for a in arts.attempts) if arts else 0
                    agent = (arts.routing_decision.action.agent_name
                             if arts and arts.routing_decision else "?")
                    reward = arts.reward.reward if arts and arts.reward else None
                    fclass = _classify_failure(status, len(state.attempt_ids))
                    cells.append({
                        "task_class": cls_name, "strategy": strat, "verification": vpol,
                        "seed": seed, "status": status, "agent": agent,
                        "attempts": len(state.attempt_ids), "cost_usd": round(cost, 4),
                        "latency_s": round(latency, 3), "tokens": tokens,
                        "reward": round(reward, 4) if reward is not None else None,
                        "failure_class": fclass,
                    })
                    # typed accumulators (avoid re-reading untyped dict values)
                    latency_total += latency
                    taxonomy[fclass] = taxonomy.get(fclass, 0) + 1
                    agents_used.add(str(agent))
                    if reward is not None:
                        rewards.append(float(reward))
                    if status == "succeeded":
                        succeeded += 1
                    elif status == "waiting_for_human":
                        human_reviews += 1

    n = len(cells)
    return {
        "config": {
            "tasks": [t[0] for t in cfg.tasks], "strategies": cfg.strategies,
            "verification_policies": cfg.verification_policies, "seeds": cfg.seeds,
        },
        "available_agents": available,
        "agents_used": sorted(agents_used),
        "unavailable_real_adapters": [
            a for a in ("claude", "codex", "openhands", "simple_llm") if a not in available
        ],
        "cells": cells,
        "summary": {
            "cells": n,
            "success_rate": round(succeeded / n, 3) if n else 0.0,
            "human_review_rate": round(human_reviews / n, 3) if n else 0.0,
            "total_latency_s": round(latency_total, 3),
            "mean_reward": round(sum(rewards) / len(rewards), 4) if rewards else 0.0,
        },
        "failure_taxonomy": taxonomy,
    }


def run_no_patch_bakeoff(service, repo_id: str, n: int = 3) -> dict:
    """Bakeoff where tasks carry NO pre-supplied patch — the agent must actually
    solve them (round-3 gap §7). The service's registry/policy decides the agent;
    plug in a true harness (or the OpenAI harness for a live run)."""
    cells = []
    for i in range(n):
        task = service.create_task(
            repo_id,
            title="Fix divide by zero",
            body="divide() returns 0 when the divisor is 0; it must raise "
                 "ZeroDivisionError. Edit calculator.py. (No patch is supplied.)",
            acceptance_criteria=["divide(x, 0) raises ZeroDivisionError"],
            metadata={},  # intentionally no 'files' patch
        )
        state = service.run_task(task.id)
        status = state.status if isinstance(state.status, str) else state.status.value
        runner = service._runners.get(state.run_id)
        traces = getattr(runner.artifacts, "agent_traces", []) if runner else []
        sel = next((t for t in traces if t.attempt_id == state.selected_attempt_id), None)
        cells.append({
            "name": f"no_patch_{i}", "status": status,
            "agent": (runner.artifacts.routing_decision.action.agent_name
                      if runner and runner.artifacts.routing_decision else "?"),
            "tool_calls": sel.tool_calls if sel else 0,
            "file_writes": sel.file_writes if sel else [],
            "solved_without_patch": status == "succeeded",
        })
    solved = sum(1 for c in cells if c["solved_without_patch"])
    return {
        "mode": "no_patch", "cells": cells,
        "summary": {"n": n, "solved": solved, "solve_rate": round(solved / max(1, n), 3)},
    }


def bakeoff_to_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# Bakeoff report", "",
        f"- cells: {s['cells']}",
        f"- success rate: {s['success_rate']}",
        f"- human-review rate: {s['human_review_rate']}",
        f"- mean reward: {s['mean_reward']}",
        f"- agents used: {report['agents_used']}",
        f"- unavailable real adapters: {report['unavailable_real_adapters']}",
        f"- failure taxonomy: {report['failure_taxonomy']}",
    ]
    return "\n".join(lines)
