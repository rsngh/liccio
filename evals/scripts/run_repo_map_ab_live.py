"""LIVE A/B: does the graph-ranked repo map help a real model on a cross-file task?

Isolates the repo-map's value (research: "the LLM can use an API exported from a module just
based on the map"). A single-shot model (ClaudeAgentAdapter, no tools to explore) must fix
checkout.py so its total matches a hidden test. The CORRECT fix is to call the canonical
``apply_house_discount`` defined in discounts.py — whose BODY (a non-obvious 0.87 factor) is
NEVER shown to the model. The buggy file hardcodes a different, wrong discount.

  - BASELINE arm: context = spec + checkout.py only. The model cannot know the house-discount
    API exists, nor its canonical value -> it guesses and fails the hidden test.
  - REPO_MAP arm: context = spec + checkout.py + the graph-ranked repo map, which exposes the
    SIGNATURE ``discounts.py: def apply_house_discount(price):`` (not its body). Knowing the API
    exists, the model calls it -> the hidden test passes.

The two arms differ ONLY by the repo-map chunk. Writes reports/live/repo_map_ab.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path

from acp.agents.claude_agent import ClaudeAgentAdapter
from acp.context.repo_map import build_repo_map
from acp.observability.live_report import redact_report
from acp.schemas.agent import Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

REPS = 3
MODEL = "claude-sonnet-4-6"

# The canonical API — its BODY (0.87) is the secret the model can only honor by CALLING it.
_DISCOUNTS = ("def apply_house_discount(price):\n"
              "    # canonical house policy — single source of truth\n"
              "    return round(price * 0.87, 2)\n")
# Buggy checkout hardcodes a DIFFERENT, wrong discount inline instead of using the API.
_CHECKOUT_BUGGY = ("def checkout_total(price):\n"
                   "    # BUG: hardcodes a discount instead of using the house policy\n"
                   "    return round(price * 0.90, 2)\n")
_ISSUE = ("checkout_total(100) returns the wrong amount. It must apply the company's canonical "
          "house discount policy (the single source of truth lives in the discounts module), "
          "not a hardcoded number. Fix checkout.py so the tests pass.")
# Hidden test: only the canonical 0.87 factor passes. 100 -> 87.0.
_TEST = ("from checkout import checkout_total\n\n"
         "def test_checkout():\n"
         "    assert checkout_total(100) == 87.0\n"
         "    assert checkout_total(50) == 43.5\n")


def _spec_item() -> ContextItem:
    return ContextItem(kind="instruction_chunk", path="__task_spec__", content=_ISSUE,
                       source="task")


def _build_repo(tmp: Path) -> Path:
    repo = tmp / "shop"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "discounts.py").write_text(_DISCOUNTS)
    (repo / "checkout.py").write_text(_CHECKOUT_BUGGY)
    (repo / "test_checkout.py").write_text(_TEST)
    (repo / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "shop"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n')
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"],
                 ["git", "config", "commit.gpgsign", "false"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "init"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)
    return repo


def _pack(arm: str, repo_id: str, task_id: str) -> ContextPack:
    items = [_spec_item(),
             ContextItem(kind="file_chunk", path="checkout.py", content=_CHECKOUT_BUGGY)]
    if arm == "repo_map":
        # graph-ranked map over the repo -> exposes the discounts API SIGNATURE (not its body)
        rmap = build_repo_map({"checkout.py": _CHECKOUT_BUGGY, "discounts.py": _DISCOUNTS},
                              token_budget=256)
        items.insert(1, ContextItem(kind="repo_map_chunk", path="__repo_map__",
                                    content=rmap.text, source="repo_map"))
    return ContextPack(repo_id=repo_id, task_id=task_id, snapshot_id="s",
                       strategy=arm, items=items)


def _run_once(adapter, arm: str, repo_path: Path, tmp: Path, i: int) -> bool:
    from git import Repo
    base = Repo(repo_path).head.commit.hexsha
    from acp.schemas.repo import Repository
    repo = Repository(name="shop", local_path=str(repo_path), default_branch="master")
    ws = LocalWorkspaceManager(tmp / f"ws_{arm}_{i}").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    task = Task(repo_id=repo.id, title="Fix checkout total", body=_ISSUE)
    pack = _pack(arm, repo.id, task.id)
    try:
        asyncio.run(adapter.execute(task, pack, ws, Budget(max_cost_usd=0.3,
                                                           max_wall_time_s=60)))
    except Exception:  # noqa: BLE001 -> counts as not solved
        return False
    proc = subprocess.run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=ws.path, capture_output=True, text=True, timeout=60, check=False)
    return proc.returncode == 0


def main() -> int:
    key = os.environ.get("ACP_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[skip] no ANTHROPIC key")
        return 0
    os.environ["ACP_ANTHROPIC_API_KEY"] = key
    adapter = ClaudeAgentAdapter(model=MODEL)
    results: dict[str, int] = {"baseline": 0, "repo_map": 0}
    with tempfile.TemporaryDirectory(prefix="acp_rmab_") as d:
        tmp = Path(d)
        repo_path = _build_repo(tmp)
        for arm in ("baseline", "repo_map"):
            for i in range(REPS):
                solved = _run_once(adapter, arm, repo_path, tmp, i)
                results[arm] += int(solved)
                print(f"  {arm:9s} rep{i}: solved={solved}")
    rates = {k: round(v / REPS, 4) for k, v in results.items()}
    report = {
        "experiment": "repo_map_ab_live",
        "what": "single-shot Claude on a cross-file task; arms differ ONLY by the repo-map chunk",
        "model": MODEL, "reps": REPS,
        "solved_by_arm": results, "solve_rate_by_arm": rates,
        "repo_map_lift": round(rates["repo_map"] - rates["baseline"], 4),
        "repo_map_helps": rates["repo_map"] > rates["baseline"],
        "evidence_tier": "fixture-unseen (authored for this eval)",
    }
    out = Path("reports/live/repo_map_ab.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for env_key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(env_key)
        if secret:
            assert secret not in out.read_text(), f"{env_key} leaked!"
    print(f"\nbaseline={rates['baseline']} repo_map={rates['repo_map']} "
          f"lift={report['repo_map_lift']} helps={report['repo_map_helps']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
