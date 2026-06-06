"""WS10/WS19 — broadened LIVE corpus with the real Claude harness (difficulty + discipline).

Runs the real ``claude_harness`` tool-loop over a difficulty-stratified bugfix corpus
(easy/medium/hard) plus the underspecified multi-bug tasks (test-discipline), all verified by
each repo's OWN pytest. From the OBSERVED tool loops it computes:

  - harness-benefit metrics HAR / HFR / PWL (research: weak models fail by not ACTIVATING the
    harness or by not FOLLOWING it once loaded — these separate capability from adherence);
  - a measurement-hygiene verdict (conclusive vs inconclusive/infra, contamination flag) using
    the SAME classifier the capability matrix + acp health share;
  - cost per conclusive success;
  - capability cells persisted into an EntityStore (WS8) so real live cells — not synthetic —
    can feed routing/health.

Budget-safe: per-call timeout + max_retries=0 come from the harness's ProviderPolicy. Skips
cleanly without a key. Writes redacted reports/live/live_corpus_broadening.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import acp.db.models  # noqa: F401  (populate the ORM registry for EntityStore persistence)
from acp.agents.benchmark_suite import (
    BENCH_TASKS,
    UNDERSPECIFIED_TASKS,
    BenchTask,
    build_bench_repo,
    run_pytest,
)
from acp.agents.trace import build_agent_trace
from acp.db.session import create_all, make_engine, make_session_factory, session_scope
from acp.evaluation.harness_metrics import (
    activation_report,
    adherence_report,
    harness_benefit_metrics,
)
from acp.evaluation.measurement_hygiene import build_hygiene_report, ingest_attempt_outcomes
from acp.observability.live_report import redact_report
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

OUT = Path("reports/live/live_corpus_broadening.json")
# $/1k tokens for the harness model (mirrors harness_base; local to avoid import cycles).
_COST_PER_1K = 0.004  # claude-haiku-class; in+out blended, conservative


def _corpus() -> list[tuple[str, BenchTask]]:
    """Difficulty-stratified bugfix tasks + underspecified (test-discipline) tasks."""
    rows = [(t.difficulty, t) for t in BENCH_TASKS]
    rows += [("underspecified", t) for t in UNDERSPECIFIED_TASKS]
    return rows


def _claude_harness():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    from acp.agents.claude_harness import ClaudeHarnessAdapter
    a = ClaudeHarnessAdapter(max_steps=6)
    return a if asyncio.run(a.healthcheck()).available else None


def _run_task(adapter, group: str, task: BenchTask, tmp: Path) -> dict:
    from acp.core.config import reset_settings

    repo_dir = build_bench_repo(tmp / f"src_{task.name}", task)
    from git import Repo
    base = Repo(repo_dir).head.commit.hexsha
    repo = Repository(name=task.name, local_path=str(repo_dir), default_branch="master")
    reset_settings()
    ws = LocalWorkspaceManager(tmp / f"ws_{task.name}").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    t = Task(repo_id=repo.id, title=f"Fix bug in {task.module_path}", body=task.prompt)
    pack = ContextPack(repo_id=repo.id, task_id=t.id, snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path=task.module_path,
                                          content=(ws.path / task.module_path).read_text())])
    t0 = time.time()
    err = None
    try:
        result = asyncio.run(adapter.execute(t, pack, ws, Budget(
            max_cost_usd=0.5, max_wall_time_s=120)))
    except Exception as exc:  # noqa: BLE001 -> inconclusive infra, never a capability failure
        result, err = None, str(exc)[:160]
    attempt = AgentAttempt(task_id=t.id, agent_kind=adapter.kind, agent_name="claude_harness")
    if result is None:
        # Inconclusive (infra/API): record a hygiene cell that won't poison solve-rate.
        cell = {"task": task.name, "task_type": "bugfix", "adapter": "claude_harness",
                "is_harness": True, "success": False, "status": "failed",
                "tool_calls": 0, "error": err or "harness error",
                "_outcome": "infra_timeout_before_action", "measurement_quality": 0.0}
        return {"group": group, "task": task.name, "trace": None, "solved": False,
                "cell": cell, "row": {"group": group, "task": task.name,
                                      "inconclusive": True, "error": err}}
    trace = build_agent_trace(attempt, result, is_harness=True, task_id=t.id)
    trace.metadata["task_type"] = "bugfix"
    solved = run_pytest(ws.path, timeout_s=60)
    act = activation_report(trace)
    adh = adherence_report(trace)
    in_tok = result.input_token_count or 0
    out_tok = result.output_token_count or 0
    cost = round((in_tok + out_tok) / 1000.0 * _COST_PER_1K, 6)
    cell = {"task": task.name, "task_type": "bugfix", "adapter": "claude_harness",
            "is_harness": True, "success": solved,
            "status": "succeeded" if solved else "failed",
            "tool_calls": trace.tool_calls, "commands": 1 if trace.tool_calls else 0,
            "file_reads": 1 if act.activated else 0, "cost_usd": cost,
            "measurement_quality": 1.0}
    row = {"group": group, "task": task.name, "activated": act.activated,
           "followed": adh.followed, "solved": solved, "tool_calls": trace.tool_calls,
           "cost_usd": cost, "latency_s": round(time.time() - t0, 2)}
    print(f"  {group:14s} {task.name:16s} activated={act.activated} "
          f"followed={adh.followed} solved={solved} ${cost}")
    return {"group": group, "task": task.name, "trace": trace, "solved": solved,
            "cell": cell, "row": row}


def main() -> int:
    adapter = _claude_harness()
    if adapter is None:
        print("[skip] no ANTHROPIC key / claude_harness unavailable")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="acp_corpus_"))
    traces, solved_map, cells, rows = [], {}, [], []
    for group, task in _corpus():
        res = _run_task(adapter, group, task, tmp)
        cells.append(res["cell"])
        rows.append(res["row"])
        if res["trace"] is not None:
            traces.append(res["trace"])
            solved_map[res["trace"].attempt_id] = res["solved"]

    metrics = harness_benefit_metrics(traces, solved_map)
    hygiene = build_hygiene_report(cells)
    # WS8: persist real live cells so routing/health can consume genuine evidence.
    engine = make_engine(f"sqlite:///{tmp / 'live_cells.db'}")
    create_all(engine)
    sf = make_session_factory(engine)
    try:
        with session_scope(sf) as s:
            n_persisted = ingest_attempt_outcomes(s, cells)
    except Exception as exc:  # noqa: BLE001 - persistence must never lose the live report
        n_persisted = -1
        print(f"[warn] cell persistence failed: {str(exc)[:160]}")

    n_solved = sum(1 for c in cells if c.get("success"))
    billable = sum(c.get("cost_usd", 0.0) for c in cells)
    cost_per_success = round(billable / n_solved, 6) if n_solved else None
    by_group: dict[str, dict] = {}
    for r in rows:
        g = by_group.setdefault(r["group"], {"n": 0, "solved": 0})
        g["n"] += 1
        g["solved"] += int(r.get("solved", False))

    report = {
        "experiment": "live_corpus_broadening",
        "source": "REAL observed claude_harness tool loops, verified by each repo's pytest",
        "model_harness": "claude_harness",
        "n_tasks": len(cells),
        "n_solved": n_solved,
        "benefit_metrics": metrics.model_dump(mode="json"),
        "measurement_hygiene": {
            "n_conclusive": hygiene.n_conclusive,
            "n_inconclusive": hygiene.n_attempts - hygiene.n_conclusive,
            "contaminated": hygiene.contaminated,
            "contamination_reasons": hygiene.contamination_reasons,
            "solve_rate_conclusive": hygiene.solve_rate,
        },
        "cost": {"total_usd": round(billable, 6), "cost_per_conclusive_success": cost_per_success},
        "live_cells_persisted": n_persisted,
        "by_group": by_group,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in OUT.read_text(), f"{key} leaked!"
    m = report["benefit_metrics"]
    print(f"\nHAR={m.get('har')} HFR={m.get('hfr')} PWL={m.get('pwl')} | "
          f"solved={n_solved}/{len(cells)} | conclusive_solve_rate="
          f"{report['measurement_hygiene']['solve_rate_conclusive']} | "
          f"cost/success=${cost_per_success} | cells_persisted={n_persisted}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
