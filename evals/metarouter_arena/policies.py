"""MetaRouter Arena — policies (GOALS Alpha 42 P0/P1/P2/P4).

A *policy* maps a task to a produced repo state, with a cost. The arena scores each on
verified success per dollar. Policies span: deterministic baselines (floor + oracle), live
context strategies (cheap single-shot vs repo_map vs tool-loop harness), and the metarouter
levers (advisor escalation, best-of-k proof-selected candidates).

All live policies use the reachable Claude adapter/harness; none require OpenAI/Gemini. Every
policy returns a normalized :class:`ArenaAttempt`; an unavailable adapter yields status
``unavailable`` (availability evidence), never a capability failure.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from pathlib import Path

from evals.metarouter_arena.schema import AdapterStatus, ArenaAttempt, ArenaTaskSpec

from acp.context.repo_map import build_repo_map
from acp.schemas.agent import Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

# Claude Sonnet-class blended pricing ($/token) for FinOps cost attribution.
_IN_PER_TOK = 3.0 / 1_000_000
_OUT_PER_TOK = 15.0 / 1_000_000


def _cost(in_tok: int, out_tok: int) -> float:
    return round((in_tok or 0) * _IN_PER_TOK + (out_tok or 0) * _OUT_PER_TOK, 6)


def _git_init(repo: Path) -> None:
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@e.com"],
                 ["git", "config", "user.name", "t"],
                 ["git", "config", "commit.gpgsign", "false"], ["git", "add", "-A"],
                 ["git", "commit", "-qm", "init"]):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)


def build_workspace(spec: ArenaTaskSpec, root: Path) -> Path:
    """A repo the agent sees: buggy module + extra files + the PUBLIC test (never the hidden)."""
    repo = root / f"ws_{spec.name}"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / spec.module_path).write_text(spec.buggy)
    for path, content in spec.extra_files.items():
        (repo / path).write_text(content)
    (repo / "test_public.py").write_text(spec.public_test)
    (repo / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n')
    (repo / "ISSUE.md").write_text(spec.issue_text)
    _git_init(repo)
    return repo


def _run_test(repo: Path, test_name: str) -> bool:
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", test_name],
        cwd=repo, capture_output=True, text=True, timeout=60, check=False, env=env)
    return proc.returncode == 0


def verify(workspace: Path, spec: ArenaTaskSpec, root: Path) -> tuple[bool, bool]:
    """Copy the agent's produced repo, inject the HELD-OUT hidden test, and verify.

    Returns (solved_hidden, solved_public). The hidden test was never visible to the agent.
    """
    ver = root / f"ver_{spec.name}_{time.time_ns()}"
    shutil.copytree(workspace, ver, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    (ver / "test_hidden.py").write_text(spec.hidden_test)
    (ver / "test_public.py").write_text(spec.public_test)
    return _run_test(ver, "test_hidden.py"), _run_test(ver, "test_public.py")


# --- deterministic baselines -----------------------------------------------------------

def policy_cheap_static(spec: ArenaTaskSpec, root: Path, **_) -> ArenaAttempt:
    """Floor: a no-op 'cheap' agent that never changes the code. Conclusive, never solved."""
    ws = build_workspace(spec, root / "cheap_static")
    solved, public = verify(ws, spec, root / "cheap_static")
    return ArenaAttempt(task=spec.name, policy="cheap_static",
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value,
                        solved=solved, public_solved=public, conclusive=True,
                        cost_usd=0.0, latency_s=0.0, detail="no-op baseline")


def policy_oracle(spec: ArenaTaskSpec, root: Path, **_) -> ArenaAttempt:
    """Ceiling: applies the reference fix. Used to compute routing regret vs oracle."""
    ws = build_workspace(spec, root / "oracle")
    (ws / spec.module_path).write_text(spec.fixed)
    solved, public = verify(ws, spec, root / "oracle")
    return ArenaAttempt(task=spec.name, policy="oracle",
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value,
                        solved=solved, public_solved=public, conclusive=True,
                        cost_usd=0.0, latency_s=0.0, changed_files=[spec.module_path],
                        detail="reference fix (oracle)")


# --- live single-shot context strategies ----------------------------------------------

def _single_shot(adapter, spec: ArenaTaskSpec, root: Path, *, strategy: str, policy_name: str,
                 guidance: str = "", temperature: float | None = None) -> ArenaAttempt:
    """Run the single-shot Claude adapter with a context pack built per `strategy`."""
    # unique per call so a policy that calls this twice (e.g. advisor retry) never collides
    call_root = root / policy_name / f"c{time.time_ns()}"
    ws = build_workspace(spec, call_root)
    body = spec.issue_text + ("\n\nADVISOR:\n" + guidance if guidance else "")
    items = [ContextItem(kind="instruction_chunk", path="__task_spec__", content=body,
                         source="task"),
             ContextItem(kind="file_chunk", path=spec.module_path, content=spec.buggy)]
    if strategy == "repo_map":
        sources = {spec.module_path: spec.buggy, **spec.extra_files}
        rmap = build_repo_map(sources, token_budget=512)
        if rmap.text:
            items.insert(1, ContextItem(kind="repo_map_chunk", path="__repo_map__",
                                        content=rmap.text, source="repo_map"))
    pack = ContextPack(repo_id="r", task_id="t", snapshot_id="s", strategy=strategy, items=items)
    repo = Repository(name=spec.name, local_path=str(ws), default_branch="master")
    from git import Repo
    base = Repo(ws).head.commit.hexsha
    wsx = LocalWorkspaceManager(call_root / "work").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    task = Task(repo_id=repo.id, title=f"Fix {spec.module_path}", body=spec.issue_text)
    t0 = time.time()
    try:
        res = asyncio.run(adapter.execute(task, pack, wsx, Budget(max_cost_usd=0.3,
                                                                  max_wall_time_s=60)))
    except Exception as exc:  # noqa: BLE001 -> inconclusive infra
        return ArenaAttempt(task=spec.name, policy=policy_name,
                            adapter_status=AdapterStatus.LIVE_INCONCLUSIVE.value, solved=False,
                            public_solved=False, conclusive=False, cost_usd=0.0,
                            latency_s=time.time() - t0, detail=str(exc)[:120])
    solved, public = verify(Path(wsx.path), spec, call_root)
    cost = _cost(res.input_token_count, res.output_token_count)
    changed = res.diff.changed_files if res.diff else []
    return ArenaAttempt(task=spec.name, policy=policy_name,
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value, solved=solved,
                        public_solved=public, conclusive=True, cost_usd=cost,
                        latency_s=round(time.time() - t0, 2), changed_files=changed)


def policy_cheap_single(spec, root, *, claude_single=None, **_) -> ArenaAttempt:
    if claude_single is None:
        return _unavailable(spec, "cheap_single", "claude adapter unavailable")
    return _single_shot(claude_single, spec, root, strategy="minimal", policy_name="cheap_single")


def policy_repo_map_router(spec, root, *, claude_single=None, **_) -> ArenaAttempt:
    if claude_single is None:
        return _unavailable(spec, "repo_map_router", "claude adapter unavailable")
    return _single_shot(claude_single, spec, root, strategy="repo_map",
                        policy_name="repo_map_router")


# --- live tool-loop harness ------------------------------------------------------------

def policy_claude_harness(spec, root, *, claude_harness=None, **_) -> ArenaAttempt:
    if claude_harness is None:
        return _unavailable(spec, "claude_harness", "claude_harness unavailable")
    from acp.agents.trace import build_agent_trace
    from acp.evaluation.harness_metrics import activation_report, adherence_report
    from acp.schemas.agent import AgentAttempt
    ws = build_workspace(spec, root / "claude_harness")
    repo = Repository(name=spec.name, local_path=str(ws), default_branch="master")
    from git import Repo
    base = Repo(ws).head.commit.hexsha
    wsx = LocalWorkspaceManager(root / "claude_harness" / f"work_{spec.name}").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    target = spec.module_path
    pack = ContextPack(repo_id=repo.id, task_id="t", snapshot_id="s",
                       items=[ContextItem(kind="file_chunk", path=target,
                                          content=(Path(wsx.path) / target).read_text())])
    task = Task(repo_id=repo.id, title=f"Fix {spec.module_path}", body=spec.issue_text)
    t0 = time.time()
    try:
        res = asyncio.run(claude_harness.execute(task, pack, wsx, Budget(max_cost_usd=0.5,
                                                                         max_wall_time_s=120)))
    except Exception as exc:  # noqa: BLE001
        return ArenaAttempt(task=spec.name, policy="claude_harness",
                            adapter_status=AdapterStatus.LIVE_INCONCLUSIVE.value, solved=False,
                            public_solved=False, conclusive=False, cost_usd=0.0,
                            latency_s=time.time() - t0, detail=str(exc)[:120])
    attempt = AgentAttempt(task_id="t", agent_kind=claude_harness.kind, agent_name="claude_harness")
    trace = build_agent_trace(attempt, res, is_harness=True, task_id="t")
    solved, public = verify(Path(wsx.path), spec, root / "claude_harness")
    return ArenaAttempt(task=spec.name, policy="claude_harness",
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value, solved=solved,
                        public_solved=public, conclusive=True,
                        cost_usd=_cost(res.input_token_count, res.output_token_count),
                        latency_s=round(time.time() - t0, 2), tool_calls=trace.tool_calls,
                        activated=activation_report(trace).activated,
                        followed=adherence_report(trace).followed,
                        changed_files=res.diff.changed_files if res.diff else [])


# --- metarouter levers: advisor escalation (P1) + best-of-k (P2) ------------------------

def policy_advisor_router(spec, root, *, claude_single=None, advise=None, **_) -> ArenaAttempt:
    """Cheap single-shot; if the public test fails, consult a read-only advisor once and retry."""
    if claude_single is None:
        return _unavailable(spec, "advisor_router", "claude adapter unavailable")
    first = _single_shot(claude_single, spec, root, strategy="minimal",
                         policy_name="advisor_router")
    if first.public_solved or advise is None:
        return first
    # escalate: advisor (read-only) proposes guidance; retry cheap executor with it
    guidance = advise(spec)
    retry = _single_shot(claude_single, spec, root, strategy="repo_map",
                         policy_name="advisor_router", guidance=guidance)
    retry.policy = "advisor_router"
    retry.advisor_calls = first.advisor_calls + 1
    retry.cost_usd = round(first.cost_usd + retry.cost_usd, 6)
    retry.latency_s = round(first.latency_s + retry.latency_s, 2)
    retry.detail = "escalated to advisor"
    return retry


def policy_best_of_k(spec, root, *, claude_single=None, k: int = 2, **_) -> ArenaAttempt:
    """Sample k cheap candidates; select by PUBLIC-test proof signal; report hidden-test verdict."""
    if claude_single is None:
        return _unavailable(spec, "best_of_k_router", "claude adapter unavailable")
    cands = [_single_shot(claude_single, spec, root, strategy="minimal",
                          policy_name=f"best_of_k_{i}") for i in range(k)]
    cost = round(sum(c.cost_usd for c in cands), 6)
    lat = round(sum(c.latency_s for c in cands), 2)
    # execution comparator: prefer a candidate whose PUBLIC test passes (the available signal)
    chosen = next((c for c in cands if c.public_solved), cands[0])
    return ArenaAttempt(task=spec.name, policy="best_of_k_router",
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value, solved=chosen.solved,
                        public_solved=chosen.public_solved, conclusive=True, cost_usd=cost,
                        latency_s=lat, candidates_sampled=k,
                        changed_files=chosen.changed_files, detail=f"best-of-{k} by public proof")


def _unavailable(spec: ArenaTaskSpec, policy: str, reason: str) -> ArenaAttempt:
    return ArenaAttempt(task=spec.name, policy=policy,
                        adapter_status=AdapterStatus.UNAVAILABLE.value, solved=False,
                        public_solved=False, conclusive=False, cost_usd=0.0, latency_s=0.0,
                        detail=reason)


def advisor_fn(claude_single):
    """Read-only advisor: short guidance from a budget-limited Claude call. Never writes."""
    def _advise(spec: ArenaTaskSpec) -> str:
        client = getattr(claude_single, "_client", lambda: None)()
        if client is None:
            return ""
        try:
            msg = client.messages.create(
                model=getattr(claude_single, "model_name", "claude-sonnet-4-6"), max_tokens=300,
                messages=[{"role": "user", "content":
                           "You are a READ-ONLY senior advisor. Do NOT write code. In 2-3 bullet "
                           "points, name the exact flaw and the fix approach (which existing API "
                           f"to call, what to import).\n\nISSUE: {spec.issue_text}\n\nBUGGY "
                           f"{spec.module_path}:\n{spec.buggy}"}])
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")[:600]
        except Exception:  # noqa: BLE001
            return ""
    return _advise


ALL_POLICIES = {
    "cheap_static": policy_cheap_static,
    "oracle": policy_oracle,
    "cheap_single": policy_cheap_single,
    "repo_map_router": policy_repo_map_router,
    "claude_harness": policy_claude_harness,
    "advisor_router": policy_advisor_router,
    "best_of_k_router": policy_best_of_k,
}
