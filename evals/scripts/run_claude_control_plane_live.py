"""LIVE: a real frontier model (Claude) driven end-to-end by the acp control plane.

This is the strongest honest demonstration of the moat loop the README describes:

    task -> context -> route -> attempt -> verify -> evaluate -> reward -> learn

For each real-world-SHAPED bug (repo-replay fixtures: semver string-vs-numeric compare,
shallow config merge, LRU recency) we:

  1. Materialize a real git repo with the BUGGY module + its failing test + an ISSUE.md.
  2. Prove the task is fair OFFLINE: buggy -> pytest FAILS, reference fix -> pytest PASSES.
     (The reference fix is never shown to the agent; it only validates the harness.)
  3. Run the FULL acp orchestration loop with ONLY the real ``ClaudeAgentAdapter`` in the
     registry, so the control plane snapshots the repo, compiles a token-budgeted context
     pack, routes (logging an action_probability), runs the model in an isolated git
     worktree, captures its diff, runs the verification plan (executes pytest), aggregates
     evidence, evaluates, computes a reward, and records the entire provenance chain.
  4. The fix is NOT handed in (unlike ``acp demo bugfix``): the model must derive it from
     the issue + buggy source alone.
  5. GENERALIZATION PROOF: re-apply the model's produced module to a fresh repo whose test
     uses DIFFERENT inputs the model never saw. Passing this rules out test-memorization.

No fix, key, or expected output is ever embedded here. Writes a redacted, secret-scanned
report to evals/reports/claude_control_plane_live.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import run_pytest
from acp.agents.claude_agent import ClaudeAgentAdapter
from acp.agents.registry import AgentRegistry
from acp.agents.repo_replay import _LRU, _MERGE, _SEMVER, RepoReplayTask
from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.observability.live_report import redact_report

MODEL = "claude-sonnet-4-6"

# Held-out generalization tests: SAME bug, DIFFERENT inputs the agent never saw. A correct
# general fix passes these; a model that overfit the visible test would not.
HOLDOUT: dict[str, str] = {
    "semver_compare": (
        "from semver import compare_versions\n\n"
        "def test_holdout():\n"
        "    assert compare_versions('1.0.10', '1.0.9') == 1\n"
        "    assert compare_versions('2.1.0', '2.0.9') == 1\n"
        "    assert compare_versions('0.9.9', '1.0.0') == -1\n"
        "    assert compare_versions('3.4.5', '3.4.5') == 0\n"
        "    assert compare_versions('1.22.0', '1.9.0') == 1\n"
    ),
    "deep_merge": (
        "from config import deep_merge\n\n"
        "def test_holdout():\n"
        "    assert deep_merge({'a': {'b': 1, 'c': 2}}, {'a': {'c': 3}}) == "
        "{'a': {'b': 1, 'c': 3}}\n"
        "    assert deep_merge({'x': {'y': {'z': 1}}}, {'x': {'y': {'w': 2}}}) == "
        "{'x': {'y': {'z': 1, 'w': 2}}}\n"
        "    assert deep_merge({'p': 1}, {'q': 2, 'r': 3}) == {'p': 1, 'q': 2, 'r': 3}\n"
    ),
    "lru_cache": (
        "from cache import LRUCache\n\n"
        "def test_holdout():\n"
        "    c = LRUCache(2)\n"
        "    c.put('x', 1)\n    c.put('y', 2)\n"
        "    assert c.get('x') == 1\n"   # touch x -> y is now LRU
        "    c.put('z', 3)\n"            # evicts y
        "    assert c.get('y') is None\n"
        "    assert c.get('x') == 1\n    assert c.get('z') == 3\n"
    ),
}

TASKS: list[RepoReplayTask] = [_SEMVER, _MERGE, _LRU]


def _git_init(repo: Path) -> None:
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"],
                 ["git", "config", "commit.gpgsign", "false"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "buggy baseline"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)


def build_repo(root: Path, task: RepoReplayTask) -> Path:
    """A real git repo: buggy module + failing test + the issue a reporter would file."""
    repo = root / f"repo_{task.name}"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / task.module_path).write_text(task.buggy)
    (repo / f"test_{task.name}.py").write_text(task.test_src)
    (repo / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
        "[tool.pytest.ini_options]\naddopts = \"-q\"\n")
    (repo / "ISSUE.md").write_text(f"# Bug report\n\n{task.issue_text}\n")
    _git_init(repo)
    return repo


def reconstruct_module(buggy_src: str, module_path: str, unified_diff: str) -> str:
    """Apply the agent's captured diff to the buggy baseline to recover the produced file.

    Robust to workspace cleanup: we never rely on the (ephemeral) worktree still existing.
    """
    if not unified_diff:
        return ""
    if not unified_diff.endswith("\n"):
        unified_diff += "\n"  # git apply rejects a patch without a trailing newline
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / module_path).write_text(buggy_src)
        (p / "patch.diff").write_text(unified_diff)
        proc = subprocess.run(["git", "apply", "-p1", "patch.diff"],
                              cwd=p, capture_output=True, text=True)
        if proc.returncode != 0:
            subprocess.run(["patch", "-p1", "-i", "patch.diff"], cwd=p,
                           capture_output=True, text=True)
        return (p / module_path).read_text()


def holdout_passes(module_path: str, module_src: str, holdout_test: str) -> bool:
    """Re-run the agent's produced module against unseen inputs (generalization proof)."""
    if not module_src:
        return False
    with tempfile.TemporaryDirectory() as d:
        h = Path(d)
        (h / module_path).write_text(module_src)
        (h / "test_holdout.py").write_text(holdout_test)
        (h / "conftest.py").write_text(
            "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
        return run_pytest(h, timeout_s=60)


def run_one(task: RepoReplayTask, workroot: Path) -> dict:
    repo_path = build_repo(workroot, task)

    # (2) Offline fairness proof: buggy FAILS, reference fix PASSES (agent never sees this).
    buggy_fails = not run_pytest(repo_path, timeout_s=60)
    ref_src = (repo_path / task.module_path).read_text()
    (repo_path / task.module_path).write_text(task.fixed)
    ref_passes = run_pytest(repo_path, timeout_s=60)
    (repo_path / task.module_path).write_text(task.buggy)  # restore buggy baseline
    subprocess.run(["git", "checkout", "-q", "--", task.module_path], cwd=repo_path,
                   check=False, capture_output=True)
    _ = ref_src

    # (3) Full control-plane loop with ONLY the real Claude adapter registered.
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{workroot / f'acp_{task.name}.db'}",
        artifact_dir=str(workroot / "artifacts"),
        workspace_dir=str(workroot / "workspaces"),
    )
    registry = AgentRegistry()
    registry.register(ClaudeAgentAdapter(name="claude", model=MODEL))
    service = AppService(settings=settings, registry=registry)

    repo = service.create_repo(f"demo-{task.name}", str(repo_path), default_branch="master")
    # The fix is NOT handed in — no metadata["files"]. The model must derive it.
    t = service.create_task(
        repo.id,
        title=f"Fix bug in {task.module_path}",
        body=task.issue_text,
        acceptance_criteria=[f"the failing test in test_{task.name}.py passes"],
    )
    state = service.run_task(t.id)
    status = state.status if isinstance(state.status, str) else state.status.value

    diffs = service.run_diff(state.run_id)
    evidence = service.run_evidence(state.run_id)
    evaluation = service.run_evaluation(state.run_id) or {}
    graph = service.full_run_graph(state.run_id)
    attempts = graph.get("attempts", [])
    routed = (graph.get("routing_decision") or {}).get("action", {})
    reward_events = graph.get("reward_events", [])

    # Recover the model's produced module from its captured diff (worktree may be gone).
    changed = diffs[0]["changed_files"] if diffs else []
    unified = diffs[0].get("unified_diff", "") if diffs else ""
    produced_module = reconstruct_module(task.buggy, task.module_path, unified)
    generalizes = holdout_passes(task.module_path, produced_module, HOLDOUT[task.name])

    _PASS = {"pass", "passed", "succeeded", "ok"}
    pytest_evidence = [e for e in evidence if "pytest" in (
        e.get("name", "") + e.get("summary", "")).lower() or e.get("kind") in (
        "unit_test", "test")]
    verified_green = status == "succeeded" and any(
        e.get("status") in _PASS for e in pytest_evidence)

    attempt = attempts[0] if attempts else {}
    return {
        "task": task.name,
        "module": task.module_path,
        "offline_fair": {"buggy_fails": buggy_fails, "reference_fix_passes": ref_passes},
        "routed_to": routed.get("agent_name"),
        "context_strategy": routed.get("context_strategy"),
        "action_probability": (graph.get("routing_decision") or {}).get("action_probability"),
        "status": status,
        "changed_files": changed,
        "verified_green_by_execution": verified_green,
        "generalizes_to_holdout": generalizes,
        "evidence": [f"{e.get('kind')}:{e.get('name')} -> {e.get('status')}"
                     for e in evidence],
        "evaluation": {"spec_compliance": evaluation.get("spec_compliance"),
                       "test_adequacy": evaluation.get("test_adequacy"),
                       "confidence": evaluation.get("confidence")},
        "reward": (reward_events[-1].get("reward") if reward_events else None),
        "tokens": {"in": attempt.get("input_token_count"),
                   "out": attempt.get("output_token_count")},
        "provenance": {
            "run_id": state.run_id, "snapshot_id": state.snapshot_id,
            "context_pack_id": state.context_pack_id,
            "routing_decision_id": state.routing_decision_id,
            "attempt_id": attempt.get("id"),
            "evaluation_result_id": state.evaluation_result_id,
            "reward_event_id": state.reward_event_id, "trace_id": state.trace_id,
        },
        "produced_diff": (diffs[0].get("unified_diff", "") if diffs else "")[:2000],
    }


def main() -> int:
    key = os.environ.get("ACP_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[skip] no ANTHROPIC key in env")
        return 0
    os.environ["ACP_ANTHROPIC_API_KEY"] = key

    rows = []
    with tempfile.TemporaryDirectory(prefix="acp_live_") as d:
        workroot = Path(d)
        for task in TASKS:
            print(f"\n=== {task.name} ({task.module_path}) ===")
            r = run_one(task, workroot)
            rows.append(r)
            print(f"  routed_to={r['routed_to']} status={r['status']} "
                  f"green={r['verified_green_by_execution']} "
                  f"generalizes={r['generalizes_to_holdout']} reward={r['reward']}")

    solved = sum(1 for r in rows
                 if r["verified_green_by_execution"] and r["generalizes_to_holdout"])
    report = {
        "experiment": "claude_control_plane_live",
        "what": "real Claude driven end-to-end by the acp control-plane loop on "
                "real-world-shaped bugs; execution-verified + generalization-tested",
        "model": MODEL,
        "evidence_tier": "fixture (real-world-shaped, not scraped repo history)",
        "n_tasks": len(rows),
        "n_solved_verified_and_generalized": solved,
        "solve_rate": round(solved / len(rows), 4) if rows else 0.0,
        "rows": rows,
    }
    out = Path("evals/reports/claude_control_plane_live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for env_key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        secret = os.environ.get(env_key)
        if secret:
            assert secret not in out.read_text(), f"{env_key} leaked!"
    print(f"\nSOLVE RATE (verified + generalized): {solved}/{len(rows)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
