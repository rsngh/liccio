"""Alpha 6, WS8 — live OpenAI harness experiment (uses OPENAI_API_KEY).

Drives the real ``OpenAIHarnessAdapter`` tool-loop on a *no-patch* bugfix in a
throwaway git repo, captures a normalized ``AgentTrace``, verifies the fix, then
writes a **redacted** artifact to ``reports/live/alpha6_openai_experiment.json``
that a reviewer can inspect without seeing prompts or secrets.

Run::

    OPENAI_API_KEY=... uv run python evals/scripts/run_live_openai_experiment.py

If the key/SDK is unavailable it prints a skip line and exits 0 so the script is
safe in CI without a key.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from git import Repo

from acp.agents.openai_harness import OpenAIHarnessAdapter
from acp.agents.trace import build_agent_trace
from acp.core.enums import RunStatus
from acp.observability.live_report import redact_report
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

OUT = Path("reports/live/alpha6_openai_experiment.json")
# A genuine no-patch task: the agent is given the buggy file as context but NOT
# the answer (no metadata.files / metadata.patch).
BUGGY = "def divide(a, b):\n    if b == 0:\n        return 0  # bug\n    return a / b\n"


def _make_workspace(tmp: Path):
    src = tmp / "repo"
    src.mkdir()
    (src / "calculator.py").write_text(BUGGY)
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    mgr = LocalWorkspaceManager(tmp / "ws")
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                    default_policy())
    return r, ws


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("[skip] no OPENAI_API_KEY in environment")
        return 0
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    from acp.core.config import reset_settings

    reset_settings()

    adapter = OpenAIHarnessAdapter(max_steps=8)
    if not asyncio.run(adapter.healthcheck()).available:
        print("[skip] openai adapter unavailable (SDK/key)")
        return 0

    tmp = Path(tempfile.mkdtemp())
    repo, ws = _make_workspace(tmp)
    task = Task(repo_id=repo.id, title="Fix divide by zero",
                body="divide() returns 0 when b==0; make it raise ZeroDivisionError. "
                     "Edit calculator.py.",
                acceptance_criteria=["divide(x, 0) raises ZeroDivisionError"])
    pack = ContextPack(repo_id=repo.id, task_id=task.id, snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path="calculator.py",
                                          content=(ws.path / "calculator.py").read_text())])
    budget = Budget(max_cost_usd=0.5, max_wall_time_s=120)

    t0 = time.time()
    result = asyncio.run(adapter.execute(task, pack, ws, budget))
    elapsed = time.time() - t0

    attempt = AgentAttempt(task_id=task.id, agent_kind=adapter.kind,
                           agent_name=adapter.name,
                           model_name=getattr(adapter, "model", None))
    trace = build_agent_trace(attempt, result, is_harness=True, task_id=task.id)

    fixed_src = (ws.path / "calculator.py").read_text()
    verified = "raise" in fixed_src or "ZeroDivisionError" in fixed_src

    report = {
        "experiment": "alpha6_live_openai_no_patch_bugfix",
        "adapter": adapter.name,
        "category": "acp_harness",
        "is_harness": True,
        "status": result.status.value if isinstance(result.status, RunStatus)
        else result.status,
        "solved": result.status == RunStatus.SUCCEEDED,
        "verified_raises_on_zero": verified,
        "trace": trace.model_dump(mode="json"),
        "metrics": {
            "tool_calls": trace.tool_calls,
            "file_writes": trace.file_writes,
            "changed_files": trace.changed_files,
            "diff_lines": trace.diff_lines,
            "input_tokens": trace.input_tokens,
            "output_tokens": trace.output_tokens,
            "estimated_cost_usd": round(trace.estimated_cost_usd, 6),
            "latency_s": round(elapsed, 3),
        },
    }
    safe = redact_report(report)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(safe, indent=2) + "\n")
    m = report["metrics"]
    print(f"solved={report['solved']} verified={verified} "
          f"tool_calls={m['tool_calls']} tokens={m['input_tokens']}+{m['output_tokens']} "
          f"cost=${m['estimated_cost_usd']:.4f} latency={m['latency_s']}s")
    print(f"wrote redacted artifact -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
