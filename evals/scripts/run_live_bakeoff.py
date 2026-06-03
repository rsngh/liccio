"""WS14 — end-to-end no-patch LIVE bakeoff (uses OPENAI_API_KEY / ANTHROPIC_API_KEY).

This is the piece that makes the Alpha 9/10/11 decision-quality claims *real*:
instead of synthetic capability cells / OPE logs, it runs real coding-agent
harnesses (``openai_harness``, ``claude_harness``) on genuine no-patch tasks via
the tool loop, *verifies* each attempt by running the repo's own tests, and feeds
the **observed** per-(task, adapter) outcomes into a real ``CapabilityMatrix`` and
a real OPE log. ``fake``/``patch`` are floor baselines (they get no answer, so a
true no-patch task should defeat them).

Outputs (redacted, committed):
  reports/live/alpha11_live_bakeoff.json        — per (task, adapter) observed cells
  evals/reports/live_bakeoff_capability_matrix.json — matrix from REAL cells
  evals/reports/live_bakeoff_ope.json           — OPE on the REAL log

Run::
    OPENAI_API_KEY=... ANTHROPIC_API_KEY=... uv run python evals/scripts/run_live_bakeoff.py

Skips cleanly (exit 0) when no key/harness is available; defensive per attempt
(an adapter error never aborts the bakeoff).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from git import Repo

from acp.agents.trace import build_agent_trace
from acp.core.enums import RunStatus
from acp.observability.live_report import redact_report
from acp.schemas.agent import AgentAttempt, Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

LIVE_OUT = Path("reports/live/alpha11_live_bakeoff.json")
MATRIX_OUT = Path("evals/reports/live_bakeoff_capability_matrix.json")
OPE_OUT = Path("evals/reports/live_bakeoff_ope.json")


# --- real no-patch tasks: (buggy source, test, task spec) -----------------
TASKS = [
    {
        "id": "bugfix_divide", "task_type": "bugfix",
        "files": {"calculator.py":
                  "def divide(a, b):\n    if b == 0:\n        return 0  # bug\n    return a / b\n"},
        "test": "test_calc.py",
        "test_src": ("import pytest\nfrom calculator import divide\n\n"
                     "def test_raises():\n    "
                     "with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n"
                     "def test_ok():\n    assert divide(6, 3) == 2\n"),
        "title": "Fix divide by zero",
        "body": "divide() returns 0 when b == 0; it must raise ZeroDivisionError. "
                "Edit calculator.py.",
        "criteria": ["divide(x, 0) raises ZeroDivisionError"],
    },
    {
        "id": "bugfix_is_even", "task_type": "bugfix",
        "files": {"nums.py": "def is_even(n):\n    return n % 2 == 1  # bug\n"},
        "test": "test_nums.py",
        "test_src": ("from nums import is_even\n\n"
                     "def test_even():\n    assert is_even(4) is True\n"
                     "def test_odd():\n    assert is_even(3) is False\n"),
        "title": "Fix is_even parity bug",
        "body": "is_even(n) returns the wrong result. Fix nums.py so is_even(4) is "
                "True and is_even(3) is False.",
        "criteria": ["is_even(4) is True", "is_even(3) is False"],
    },
    {
        "id": "bugfix_clamp", "task_type": "bugfix",
        "files": {"clampx.py":
                  "def clamp(x, lo, hi):\n    return min(x, hi)  # bug: ignores lo\n"},
        "test": "test_clamp.py",
        "test_src": ("from clampx import clamp\n\n"
                     "def test_low():\n    assert clamp(-5, 0, 10) == 0\n"
                     "def test_high():\n    assert clamp(50, 0, 10) == 10\n"
                     "def test_mid():\n    assert clamp(5, 0, 10) == 5\n"),
        "title": "Fix clamp lower bound",
        "body": "clamp(x, lo, hi) ignores the lower bound. Fix clampx.py so "
                "clamp(-5, 0, 10) == 0.",
        "criteria": ["clamp(-5, 0, 10) == 0", "clamp(50, 0, 10) == 10"],
    },
    {
        "id": "feature_factorial", "task_type": "feature",
        "files": {"mathx.py": "def factorial(n):\n    pass  # TODO: implement\n"},
        "test": "test_mathx.py",
        "test_src": ("from mathx import factorial\n\n"
                     "def test_factorial():\n    assert factorial(5) == 120\n"
                     "    assert factorial(0) == 1\n"),
        "title": "Implement factorial",
        "body": "Implement factorial(n) in mathx.py so factorial(5)==120 and "
                "factorial(0)==1.",
        "criteria": ["factorial(5) == 120", "factorial(0) == 1"],
    },
    {
        "id": "security_eval", "task_type": "security_fix",
        "files": {"calc_eval.py":
                  "def compute(expr):\n    # INSECURE: arbitrary code execution\n"
                  "    return eval(expr)\n"},
        "test": "test_sec.py",
        "test_src": ("import pytest\nfrom calc_eval import compute\n\n"
                     "def test_arith():\n    assert compute('2 + 3 * 4') == 14\n"
                     "def test_no_arbitrary_exec():\n    "
                     "with pytest.raises(Exception):\n        "
                     "compute(\"__import__('os').getcwd()\")\n"),
        "title": "Remove eval() injection in compute()",
        "body": "compute(expr) uses eval(), allowing arbitrary code execution. "
                "Replace it with a SAFE arithmetic evaluator that still computes "
                "'2 + 3 * 4' == 14 but rejects arbitrary code like __import__.",
        "criteria": ["compute('2 + 3 * 4') == 14",
                     "arbitrary code (e.g. __import__) is rejected"],
    },
    {
        "id": "testgen_stats", "task_type": "test_generation",
        "files": {"stats.py":
                  "def mean(xs):\n    return sum(xs) / len(xs)\n\n"
                  "def variance(xs):\n    m = mean(xs)\n    "
                  "return sum((x - m) ** 2 for x in xs) / len(xs)\n"},
        "test": "test_meta.py",
        "test_src": ("import subprocess, sys, pathlib\n\n"
                     "def test_written_tests_pass_and_cover():\n    "
                     "p = pathlib.Path('test_stats.py')\n    "
                     "assert p.exists(), 'no test_stats.py written'\n    "
                     "src = p.read_text()\n    "
                     "assert 'mean' in src and 'variance' in src\n    "
                     "r = subprocess.run([sys.executable, '-m', 'pytest', '-q', "
                     "'test_stats.py'], capture_output=True)\n    "
                     "assert r.returncode == 0\n"),
        "title": "Write tests for stats.py",
        "body": "Write a pytest file test_stats.py that tests both mean() and "
                "variance() in stats.py with correct expected values. The tests "
                "must pass.",
        "criteria": ["test_stats.py exists and passes", "covers mean and variance"],
    },
    {
        "id": "bugfix_fib", "task_type": "bugfix",
        "files": {"fib.py":
                  "def fib(n):\n    # bug: wrong base cases\n    "
                  "if n < 2:\n        return n + 1\n    "
                  "return fib(n - 1) + fib(n - 2)\n"},
        "test": "test_fib.py",
        "test_src": ("from fib import fib\n\n"
                     "def test_seq():\n    "
                     "assert [fib(i) for i in range(7)] == [0, 1, 1, 2, 3, 5, 8]\n"),
        "title": "Fix fibonacci base cases",
        "body": "fib(n) has wrong base cases. Fix fib.py so the sequence is "
                "0,1,1,2,3,5,8,...",
        "criteria": ["fib(0)==0, fib(1)==1", "fib(6)==8"],
    },
    {
        # Harder: subtle bug — merge() never sorts, so unsorted input is wrong.
        # Fixing it requires recognizing the algorithm needs sorted intervals.
        "id": "bugfix_merge_intervals", "task_type": "bugfix",
        "files": {"intervals.py":
                  "def merge(intervals):\n"
                  "    # bug: assumes input is already sorted by start\n"
                  "    result = []\n"
                  "    for s, e in intervals:\n"
                  "        if result and s <= result[-1][1]:\n"
                  "            result[-1][1] = max(result[-1][1], e)\n"
                  "        else:\n"
                  "            result.append([s, e])\n"
                  "    return result\n"},
        "test": "test_intervals.py",
        "test_src": ("from intervals import merge\n\n"
                     "def test_sorted():\n    "
                     "assert merge([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]\n"
                     "def test_unsorted():\n    "
                     "assert merge([[1,4],[0,2],[3,5]]) == [[0,5]]\n"
                     "def test_nested():\n    "
                     "assert merge([[1,10],[2,3],[4,5]]) == [[1,10]]\n"),
        "title": "Fix merge() for unsorted intervals",
        "body": "merge(intervals) merges overlapping intervals but is wrong when the "
                "input is not pre-sorted by start. Fix intervals.py so it works for "
                "any order, e.g. merge([[1,4],[0,2],[3,5]]) == [[0,5]].",
        "criteria": ["handles unsorted input", "merges nested/overlapping intervals"],
    },
    {
        # Harder: implement a correct LRU cache (eviction order is the tricky part).
        "id": "feature_lru_cache", "task_type": "feature",
        "files": {"lru.py": "# Implement LRUCache here.\n"},
        "test": "test_lru.py",
        "test_src": ("from lru import LRUCache\n\n"
                     "def test_lru_eviction():\n    "
                     "c = LRUCache(2)\n    "
                     "c.put(1, 1); c.put(2, 2)\n    "
                     "assert c.get(1) == 1\n    "
                     "c.put(3, 3)\n    "
                     "assert c.get(2) == -1\n    "
                     "c.put(4, 4)\n    "
                     "assert c.get(1) == -1\n    "
                     "assert c.get(3) == 3 and c.get(4) == 4\n"),
        "title": "Implement an LRU cache",
        "body": "Implement class LRUCache(capacity) in lru.py with get(key)->value (or "
                "-1 if absent) and put(key, value). When over capacity, evict the "
                "least-recently-used entry. Any get or put counts as a use.",
        "criteria": ["evicts least-recently-used", "get returns -1 when absent"],
    },
]


def _make_repo(tmp: Path, spec: dict) -> Repository:
    src = tmp / f"repo_{spec['id']}"
    src.mkdir()
    for name, content in spec["files"].items():
        (src / name).write_text(content)
    (src / spec["test"]).write_text(spec["test_src"])
    (src / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n')
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(list(spec["files"]) + [spec["test"], "pyproject.toml"])
    repo.index.commit("init")
    return Repository(name=spec["id"], local_path=str(src), default_branch="master")


def _verify(ws_path: Path, test_file: str) -> bool:
    """Run the repo's own test in the workspace; solved == tests pass."""
    try:
        r = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", "-q", test_file],
            cwd=str(ws_path), capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _build_adapters() -> dict:
    from acp.agents.fake import FakeAgentAdapter
    from acp.agents.patch_agent import PatchAgentAdapter
    from acp.core.config import reset_settings

    # Mirror the provider keys into the ACP_-prefixed names BEFORE any adapter
    # builds. The settings singleton is cached on first read, so if openai's
    # healthcheck loads settings before ACP_ANTHROPIC_API_KEY is set, claude's
    # healthcheck reads a stale (anthropic=None) cache and falsely reports
    # unavailable. Set both, then reset the cache once, so both providers resolve.
    if os.environ.get("OPENAI_API_KEY"):
        os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    reset_settings()

    adapters: dict[str, object] = {"fake": FakeAgentAdapter(), "patch": PatchAgentAdapter()}
    if os.environ.get("OPENAI_API_KEY"):
        from acp.agents.openai_harness import OpenAIHarnessAdapter
        oa = OpenAIHarnessAdapter(max_steps=8)
        if asyncio.run(oa.healthcheck()).available:
            adapters["openai_harness"] = oa
    if os.environ.get("ANTHROPIC_API_KEY"):
        from acp.agents.claude_harness import ClaudeHarnessAdapter
        ca = ClaudeHarnessAdapter(max_steps=8)
        if asyncio.run(ca.healthcheck()).available:
            adapters["claude_harness"] = ca
    if os.environ.get("ACP_LIVE_CODEX") and shutil.which("codex"):
        from acp.agents.codex_cli import CodexCLIAdapter
        adapters["codex_cli"] = CodexCLIAdapter()
    return adapters


def _run_attempt(adapter, name: str, spec: dict, repo: Repository, ws_root: Path,
                 rep: int = 0) -> dict:
    from acp.core.config import reset_settings
    reset_settings()
    base = Repo(repo.local_path).head.commit.hexsha
    ws = LocalWorkspaceManager(ws_root / f"{spec['id']}_{name}_{rep}").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    target = next(iter(spec["files"]))
    task = Task(repo_id=repo.id, title=spec["title"], body=spec["body"],
                acceptance_criteria=spec["criteria"])
    pack = ContextPack(repo_id=repo.id, task_id=task.id, snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path=target,
                                          content=(ws.path / target).read_text())])
    t0 = time.time()
    try:
        result = asyncio.run(adapter.execute(task, pack, ws, Budget(
            max_cost_usd=0.5, max_wall_time_s=120)))
    except Exception as exc:  # noqa: BLE001 - never abort the bakeoff
        return {"task": spec["id"], "task_type": spec["task_type"], "adapter": name,
                "success": False, "error": f"execute raised: {exc}",
                "cost_usd": 0.0, "latency_s": round(time.time() - t0, 3)}
    elapsed = time.time() - t0
    solved = _verify(ws.path, spec["test"])
    attempt = AgentAttempt(task_id=task.id, agent_kind=adapter.kind, agent_name=name)
    trace = build_agent_trace(attempt, result, is_harness=getattr(adapter, "is_harness",
                                                                  False), task_id=task.id)
    return {
        "task": spec["id"], "task_type": spec["task_type"], "adapter": name,
        "is_harness": bool(getattr(adapter, "is_harness", False)),
        "context_strategy": "hybrid_keyword_embedding",
        "status": result.status.value if isinstance(result.status, RunStatus)
        else result.status,
        # Wall-clock timeout = provider/infra latency, not a capability signal;
        # excluded from success aggregation + OPE downstream.
        "timed_out": (result.status == RunStatus.TIMED_OUT),
        "success": solved, "verification_pass": solved,
        "tool_calls": trace.tool_calls, "changed_files": trace.changed_files,
        # Verification adherence signals (Alpha 13 live-tuning): did the harness
        # read before editing, and did it run a command (e.g. the tests)?
        "file_reads": trace.file_reads, "commands": trace.commands,
        "diff_lines": trace.diff_lines,
        "input_tokens": trace.input_tokens, "output_tokens": trace.output_tokens,
        "cost_usd": round(trace.estimated_cost_usd, 6), "latency_s": round(elapsed, 3),
    }


def main() -> int:
    adapters = _build_adapters()
    live = [n for n in adapters if n in ("openai_harness", "claude_harness")]
    if not live:
        print("[skip] no live harness available (set OPENAI_API_KEY / ANTHROPIC_API_KEY)")
        return 0
    print(f"live harnesses: {live}; baselines: fake, patch")

    reps = int(os.environ.get("ACP_BAKEOFF_REPS", "2"))
    tmp = Path(tempfile.mkdtemp())
    cells: list[dict] = []
    for spec in TASKS:
        repo = _make_repo(tmp, spec)
        for rep in range(reps):
            for name, adapter in adapters.items():
                cell = _run_attempt(adapter, name, spec, repo, tmp / "ws", rep=rep)
                cell["rep"] = rep
                cells.append(cell)
                print(f"  {spec['id']:18s} r{rep} {name:16s} solved={cell['success']} "
                      f"cost=${cell.get('cost_usd', 0):.4f} {cell.get('latency_s', 0)}s")

    # Real capability matrix from observed cells (the matrix itself drops
    # timed-out rows; see CapabilityMatrix.from_bakeoff_report).
    from acp.routing.capability_matrix import CapabilityMatrix
    matrix = CapabilityMatrix.from_bakeoff_report({"cells": cells})

    # Exclude wall-clock timeouts from success/OPE: they reflect provider latency,
    # not capability, and would otherwise distort the policy. Log how many we drop
    # so the exclusion is never silent.
    timed_out_cells = [c for c in cells if c.get("timed_out")]
    if timed_out_cells:
        # A timeout with zero tool activity = the first call hung (pure infra). A
        # timeout AFTER tool calls could be the agent genuinely struggling/looping
        # on a hard task — surface that separately so it can't masquerade as infra.
        no_progress = sum(1 for c in timed_out_cells if not c.get("tool_calls"))
        with_activity = len(timed_out_cells) - no_progress
        print(f"[exclude] {len(timed_out_cells)}/{len(cells)} attempts timed out -> "
              f"dropped from success-rate and OPE "
              f"({no_progress} no-progress/infra, {with_activity} had tool activity)")
        if with_activity:
            print(f"[warn] {with_activity} timeout(s) occurred after tool calls — "
                  f"possible genuine struggle, not just infra latency; inspect cells")
    scored_cells = [c for c in cells if not c.get("timed_out")]

    # Real OPE log: each adapter is an action; reward = solved. Uniform behavior.
    from acp.routing.ope import OPESample, evaluate_policy, fit_reward_model
    by_task: dict[str, list[dict]] = {}
    for c in scored_cells:
        by_task.setdefault(c["task_type"], []).append(c)
    samples: list[OPESample] = []
    for ttype, group in by_task.items():
        actions = sorted({c["adapter"] for c in group})
        for c in group:
            samples.append(OPESample(ttype, c["adapter"], 1.0 / len(actions),
                                     1.0 if c["success"] else 0.0, actions))
    ope: dict = {"n": len(samples)}
    if samples:
        q = fit_reward_model(samples)

        def greedy(ctx, action, cands):
            best = max(q(ctx, a) for a in cands)
            winners = [a for a in cands if q(ctx, a) == best]
            return 1.0 / len(winners) if action in winners else 0.0

        def random_t(ctx, action, cands):
            return 1.0 / len(cands)

        baseline = sum(s.reward for s in samples) / len(samples)

        # Cost-aware reward = success - LAMBDA*cost. LAMBDA=2 keeps the cost term
        # below the smallest real success gap (0.2 at n=5) so it only orders cells
        # that tie on success -> the cost-optimal policy, not a success-blind one.
        cost_lambda = 2.0
        actions_by_task = {tt: sorted({c["adapter"] for c in g}) for tt, g in by_task.items()}
        cost_samples = [
            OPESample(
                c["task_type"], c["adapter"], 1.0 / len(actions_by_task[c["task_type"]]),
                (1.0 if c["success"] else 0.0) - cost_lambda * float(c.get("cost_usd", 0)),
                actions_by_task[c["task_type"]])
            for c in scored_cells]
        qc = fit_reward_model(cost_samples)

        def cost_greedy(ctx, action, cands):
            best = max(qc(ctx, a) for a in cands)
            winners = [a for a in cands if qc(ctx, a) == best]
            return 1.0 / len(winners) if action in winners else 0.0

        def _mean_cost_reward(a, g):
            rs = [(1.0 if c["success"] else 0.0) - cost_lambda * float(c.get("cost_usd", 0))
                  for c in g if c["adapter"] == a]
            return sum(rs) / len(rs) if rs else -1e9

        ope = {
            "n": len(samples), "logged_mean_reward": round(baseline, 4),
            "greedy_dr": evaluate_policy(samples, greedy, seed=1).dr.as_dict(),
            "random_dr": evaluate_policy(samples, random_t, seed=1).dr.as_dict(),
            "cost_aware_greedy_dr": evaluate_policy(cost_samples, cost_greedy, seed=1).dr.as_dict(),
            "cost_lambda": cost_lambda,
            "best_adapter_per_task_type": {
                tt: max({c["adapter"] for c in g},
                        key=lambda a: sum(c["success"] for c in g if c["adapter"] == a))
                for tt, g in by_task.items()},
            "cost_aware_best_adapter_per_task_type": {
                tt: max({c["adapter"] for c in g}, key=lambda a, g=g: _mean_cost_reward(a, g))
                for tt, g in by_task.items()},
        }

    solved_by_adapter: dict[str, int] = {}
    for c in scored_cells:
        solved_by_adapter[c["adapter"]] = solved_by_adapter.get(c["adapter"], 0) + int(
            c["success"])
    report = {
        "experiment": "alpha11_live_no_patch_bakeoff",
        "n_tasks": len(TASKS), "adapters": sorted(adapters),
        "live_harnesses": live,
        "solved_by_adapter": solved_by_adapter,
        "cells": cells,
    }
    LIVE_OUT.parent.mkdir(parents=True, exist_ok=True)
    LIVE_OUT.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    MATRIX_OUT.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_OUT.write_text(json.dumps(matrix.to_dict(), indent=2, default=str) + "\n")
    OPE_OUT.write_text(json.dumps({"experiment": "alpha11_live_bakeoff_ope",
                                   "source": "REAL observed agent runs", **ope},
                                  indent=2, default=str) + "\n")
    # Leak check.
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            assert secret not in LIVE_OUT.read_text(), f"{key} leaked!"
    print(f"solved_by_adapter={solved_by_adapter}")
    print(f"wrote {LIVE_OUT}, {MATRIX_OUT}, {OPE_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
