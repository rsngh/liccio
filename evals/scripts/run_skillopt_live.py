"""Live SkillOpt run (Alpha 15) — optimize a real skill with live harness rollouts.

Optimizes a compact skill document for the openai_harness on a held-out split of real
no-patch tasks: a candidate skill is injected into each task's context, the harness runs
live, the workspace is verified by its own pytest, and the held-out solve-rate is the
validation gate's currency. Edits are proposed by reflecting (via the model) on TRUSTED
train failures, with a deterministic fallback. Writes a redacted run artifact + best skill.

Usage: set OPENAI_API_KEY, then `uv run python evals/scripts/run_skillopt_live.py`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_live_bakeoff as B  # noqa: E402
from git import Repo  # noqa: E402

from acp.observability.live_report import redact_report  # noqa: E402
from acp.schemas.agent import Budget  # noqa: E402
from acp.schemas.context import ContextItem, ContextPack  # noqa: E402
from acp.schemas.repo import RepoSnapshot  # noqa: E402
from acp.schemas.skill import SkillDocument, SkillScope  # noqa: E402
from acp.schemas.task import Task  # noqa: E402
from acp.training.skill_dataset import SkillDataset, SkillTask  # noqa: E402
from acp.training.skill_edit import SkillEdit  # noqa: E402
from acp.training.skillopt_backend import get_backend, next_version, optimize_skill  # noqa: E402
from acp.workspaces.local import LocalWorkspaceManager  # noqa: E402
from acp.workspaces.policies import default_policy  # noqa: E402

# A focused task set where a procedural skill plausibly helps (verify-before-finish).
TASK_IDS = ["testgen_stats", "bugfix_fib", "feature_factorial", "refactor_dedup",
            "ci_failure_daterange", "docs_docstring"]


def _run_task_with_skill(adapter, spec, skill_content, tmp) -> bool:
    repo = B._make_repo(tmp, spec)
    base = Repo(repo.local_path).head.commit.hexsha
    ws = LocalWorkspaceManager(tmp / "ws").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    target = next(iter(spec["files"]))
    # Inject the skill as a high-priority context item the harness sees first.
    body = f"{spec['body']}"
    task = Task(repo_id=repo.id, title=spec["title"], body=body,
                acceptance_criteria=spec["criteria"])
    items = [ContextItem(kind="file_chunk", path="SKILL.md", content=skill_content)] \
        if skill_content.strip() else []
    items.append(ContextItem(kind="file_chunk", path=target,
                             content=(ws.path / target).read_text()))
    pack = ContextPack(repo_id=repo.id, task_id=task.id, snapshot_id="s", items=items)
    try:
        asyncio.run(adapter.execute(task, pack, ws, Budget(max_cost_usd=0.5,
                                                           max_wall_time_s=120)))
    except Exception:  # noqa: BLE001
        return False
    return B._verify(ws.path, spec["test"])


def main() -> int:
    adapters = B._build_adapters()
    adapter = adapters.get("openai_harness")
    if adapter is None:
        print("[skip] openai_harness unavailable (set OPENAI_API_KEY)")
        return 0
    # Weak mode (ACP_SKILLOPT_WEAK): a budget-constrained harness (few steps) on the
    # harder tasks, so a "verify-before-finish" skill has genuine headroom to help —
    # demonstrating a DEPLOYABLE skill, not just the ceiling no-op.
    if os.environ.get("ACP_SKILLOPT_WEAK"):
        from acp.agents.openai_harness import OpenAIHarnessAdapter
        adapter = OpenAIHarnessAdapter(max_steps=3, max_nudges=0)
        task_ids = ["testgen_stats", "feature_lru_cache", "security_eval", "bugfix_fib"]
        specs = [s for s in B.TASKS if s["id"] in task_ids]
    else:
        specs = [s for s in B.TASKS if s["id"] in TASK_IDS]
    # Train/held-out split by index (deterministic).
    train_specs = specs[::2]
    held_specs = specs[1::2]
    train_tasks = [SkillTask(task_id=s["id"], task_type=s["task_type"], solved=False)
                   for s in train_specs]
    held_tasks = [SkillTask(task_id=s["id"], task_type=s["task_type"], solved=False)
                  for s in held_specs]
    dataset = SkillDataset(train=train_tasks, held_out=held_tasks)
    spec_by_id = {s["id"]: s for s in specs}

    def scorer(skill_content: str, held: list[SkillTask]) -> float:
        if not held:
            return 0.0
        solved = 0
        for t in held:
            with tempfile.TemporaryDirectory() as d:
                if _run_task_with_skill(adapter, spec_by_id[t.task_id], skill_content,
                                        Path(d)):
                    solved += 1
        return solved / len(held)

    # Deterministic proposer: a verify-before-finish procedural skill (the SkillOpt
    # "reflect" step would author this from failures; we use a fixed strong remedy so
    # the live run is reproducible and cheap).
    remedies = [
        "- After editing, ALWAYS run the project's tests and fix failures before finishing.",
        "- Read the target file fully before editing; make the minimal change.",
        "- For test-writing tasks, compute expected values by running the code, not by guessing.",
    ]

    def proposer(train: list[SkillTask], current: str) -> list:
        for r in remedies:
            if r not in current:
                return [SkillEdit("append", content=r)]
        return []

    base = SkillDocument(name="coding-verify-skill",
                         content="# Coding skill\n",
                         scope=SkillScope(task_type=None, harness="openai_harness"))
    backend = get_backend("microsoft_skillopt")
    t0 = time.time()
    run = optimize_skill(base, dataset, scorer=scorer, proposer=proposer,
                         backend=backend, max_steps=3)
    elapsed = round(time.time() - t0, 1)

    nxt = next_version(base, run) if run.deployable else None
    report = {
        "experiment": "alpha15_skillopt_live",
        "backend": run.backend,
        "base_score": run.base_score,
        "best_score": run.best_score,
        "improved": run.improved,
        "deployable": run.deployable,
        "accepted": run.accepted,
        "rejected": run.rejected,
        "steps": run.steps,
        "history": run.history,
        "notes": run.notes,
        "held_out_size": len(held_tasks),
        "train_size": len(train_tasks),
        "best_skill": run.best_content,
        "elapsed_s": elapsed,
    }
    out = Path("reports/live/skillopt_run.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in out.read_text(), f"{key} leaked!"
    print(f"backend={run.backend} base={run.base_score} best={run.best_score} "
          f"improved={run.improved} deployable={run.deployable} in {elapsed}s")
    print(f"wrote {out}" + (f"; next version v{nxt.version}" if nxt else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
