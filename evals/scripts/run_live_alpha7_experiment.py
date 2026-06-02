"""Alpha 7 live experiment (WS19, uses OPENAI_API_KEY).

End-to-end decision-quality slice on a real run: assess viability of a no-patch
bugfix, have the real ``openai_harness`` solve it, distill a redacted *repair*
training example from the resulting diff, and emit a committed redacted artifact
``reports/live/alpha7_openai_experiment.json``.

Skips cleanly (exit 0) without a key.
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
from acp.core.classifier import classify
from acp.core.enums import RunStatus
from acp.core.viability import assess_viability
from acp.observability.live_report import redact_report
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

OUT = Path("reports/live/alpha7_openai_experiment.json")
BUGGY = "def divide(a, b):\n    if b == 0:\n        return 0  # bug\n    return a / b\n"


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("[skip] no OPENAI_API_KEY")
        return 0
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    from acp.core.config import reset_settings

    reset_settings()
    adapter = OpenAIHarnessAdapter(max_steps=8)
    if not asyncio.run(adapter.healthcheck()).available:
        print("[skip] openai adapter unavailable")
        return 0

    tmp = Path(tempfile.mkdtemp())
    src = tmp / "repo"
    src.mkdir()
    (src / "calculator.py").write_text(BUGGY)
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")
    r = Repository(name="d", local_path=str(src), default_branch="master")
    ws = LocalWorkspaceManager(tmp / "ws").create(
        r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
        default_policy())

    task = Task(repo_id=r.id, title="Fix divide by zero",
                body="divide() returns 0 when b==0; make it raise ZeroDivisionError. "
                     "Edit calculator.py.",
                acceptance_criteria=["divide(x, 0) raises ZeroDivisionError"])

    # 1. Viability assessment (decision quality before acting).
    viability = assess_viability(task, classify(task))

    # 2. Real harness solves the task.
    pack = ContextPack(repo_id=r.id, task_id=task.id, snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path="calculator.py",
                                          content=(ws.path / "calculator.py").read_text())])
    t0 = time.time()
    result = asyncio.run(adapter.execute(task, pack, ws, Budget(max_cost_usd=0.5,
                                                                max_wall_time_s=120)))
    elapsed = time.time() - t0
    attempt = AgentAttempt(task_id=task.id, agent_kind=adapter.kind,
                           agent_name=adapter.name)
    trace = build_agent_trace(attempt, result, is_harness=True, task_id=task.id)
    fixed_src = (ws.path / "calculator.py").read_text()
    verified = "raise" in fixed_src or "ZeroDivisionError" in fixed_src

    # 3. Distill a redacted repair training example from the exhaust.
    training_example = {
        "dataset_kind": "repair",
        "task_id": task.id,
        "inputs": {"task": task.title, "acceptance_criteria": task.acceptance_criteria},
        "target_changed_files": trace.changed_files,
        "label_source": "objective",
        "solved": result.status == RunStatus.SUCCEEDED and verified,
    }

    report = {
        "experiment": "alpha7_live_openai_decision_slice",
        "viability": {
            "task_type": getattr(viability.task_type, "value", viability.task_type),
            "true_harness_required": viability.true_harness_required,
            "human_review_required": viability.human_review_required,
            "viable_context_strategies": viability.viable_context_strategies,
            "abstain": viability.abstain,
            "confidence": viability.confidence,
        },
        "harness_run": {
            "adapter": adapter.name,
            "status": result.status.value if isinstance(result.status, RunStatus)
            else result.status,
            "solved": result.status == RunStatus.SUCCEEDED,
            "verified_raises_on_zero": verified,
            "tool_calls": trace.tool_calls,
            "changed_files": trace.changed_files,
            "diff_lines": trace.diff_lines,
            "input_tokens": trace.input_tokens,
            "output_tokens": trace.output_tokens,
            "estimated_cost_usd": round(trace.estimated_cost_usd, 6),
            "latency_s": round(elapsed, 3),
        },
        "distilled_training_example": training_example,
    }
    safe = redact_report(report)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(safe, indent=2) + "\n")
    print(f"viability harness_required={viability.true_harness_required} "
          f"solved={report['harness_run']['solved']} verified={verified} "
          f"cost=${report['harness_run']['estimated_cost_usd']:.4f} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
