"""Live A/B skill canary (Round 17) — statistically validate a skill online.

Routes held-out tasks through a weakened openai_harness with the candidate skill
injected (canary) vs without (control), collecting per-attempt cells (success + harness
signals) so the measurement-trust layer classifies each outcome. Then runs the
two-proportion canary gate and only "promotes" on a significant conclusive-solve lift.
Real rollouts, repo-pytest verified, bounded spend, redacted artifact.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_live_bakeoff as B  # noqa: E402
from git import Repo  # noqa: E402

from acp.core.enums import RunStatus  # noqa: E402
from acp.observability.live_report import redact_report  # noqa: E402
from acp.schemas.agent import Budget  # noqa: E402
from acp.schemas.context import ContextItem, ContextPack  # noqa: E402
from acp.schemas.repo import RepoSnapshot  # noqa: E402
from acp.schemas.task import Task  # noqa: E402
from acp.training.skill_canary import evaluate_ab_canary  # noqa: E402
from acp.workspaces.local import LocalWorkspaceManager  # noqa: E402
from acp.workspaces.policies import default_policy  # noqa: E402

SKILL = ("# Coding skill\n"
         "- After editing, ALWAYS run the project's tests and fix failures before finishing.\n")
TASK_IDS = ["testgen_stats", "bugfix_fib"]
REPS = 3


def _run_cell(adapter, spec, skill_content, tmp) -> dict:
    repo = B._make_repo(tmp, spec)
    base = Repo(repo.local_path).head.commit.hexsha
    ws = LocalWorkspaceManager(tmp / "ws").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    target = next(iter(spec["files"]))
    task = Task(repo_id=repo.id, title=spec["title"], body=spec["body"],
                acceptance_criteria=spec["criteria"])
    items = [ContextItem(kind="file_chunk", path="SKILL.md", content=skill_content)] \
        if skill_content.strip() else []
    items.append(ContextItem(kind="file_chunk", path=target,
                             content=(ws.path / target).read_text()))
    pack = ContextPack(repo_id=repo.id, task_id=task.id, snapshot_id="s", items=items)
    status, tool_calls, error = "failed", 0, None
    try:
        res = asyncio.run(adapter.execute(task, pack, ws,
                                          Budget(max_cost_usd=0.5, max_wall_time_s=120)))
        status = res.status.value if isinstance(res.status, RunStatus) else str(res.status)
        tool_calls = len(res.tool_calls or [])
        error = res.error
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    solved = B._verify(ws.path, spec["test"])
    return {"task_type": spec["task_type"], "adapter": "openai_harness", "is_harness": True,
            "success": solved, "status": status, "tool_calls": tool_calls,
            "commands": 1 if tool_calls else 0, "file_reads": 1 if tool_calls else 0,
            "timed_out": status == "timed_out", "error": error}


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("[skip] OPENAI_API_KEY unset")
        return 0
    from acp.agents.openai_harness import OpenAIHarnessAdapter
    adapter = OpenAIHarnessAdapter(max_steps=3, max_nudges=0)
    specs = [s for s in B.TASKS if s["id"] in TASK_IDS]

    def arm(skill_content):
        cells = []
        for spec in specs:
            for _ in range(REPS):
                with tempfile.TemporaryDirectory() as d:
                    cells.append(_run_cell(adapter, spec, skill_content, Path(d)))
        return cells

    control = arm("")
    canary = arm(SKILL)
    res = evaluate_ab_canary(control, canary, min_per_arm=4, alpha=0.05)
    report = {
        "experiment": "round17_skill_canary_live", "skill": SKILL,
        "control_rate": res.control_rate, "canary_rate": res.canary_rate,
        "control_n": res.control_n, "canary_n": res.canary_n, "lift": res.lift,
        "z_score": res.z_score, "p_value": res.p_value, "significant": res.significant,
        "contaminated": res.contaminated, "promote": res.promote, "reasons": res.reasons,
    }
    out = Path("reports/live/skill_canary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"canary: control={res.control_rate} canary={res.canary_rate} lift={res.lift} "
          f"p={res.p_value} promote={res.promote}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
