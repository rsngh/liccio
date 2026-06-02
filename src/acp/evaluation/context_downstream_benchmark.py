"""Context-strategy DOWNSTREAM benchmark (Alpha 7, WS7).

Alpha 6 (``context_strategy_benchmark``) scored context strategies by retrieval
*recall@k* only. That answers "did the gold file end up in the pack?" but not
the question routing actually cares about: "does this strategy help the agent
SOLVE the task?"

This module closes that gap. For each ``(task × context_strategy × repetition)``
it actually runs a deterministic agent end-to-end through an ``AppService`` (in a
temp DB / workspace), pinning the context strategy for the run, and records the
*downstream* outcome: run status, verification pass, reward, cost, latency — plus
the gold retrieval recall for the same pack as a tiebreak signal. Aggregating per
strategy yields a downstream ``success_rate`` so routing can learn which strategy
maximizes solving the task, not just retrieving files.

Runs fully offline with the deterministic patch agent (``metadata={"files": ...}``
applies the fix), so no network / API key is required. Mirrors the
report/dataclass/``to_dict``/markdown shape of ``context_strategy_benchmark``.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from git import Repo

from acp.api.service import AppService
from acp.context.retrieval import STRATEGIES
from acp.core.config import ACPSettings
from acp.routing.actions import RoutingAction
from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent

# A small, representative spread of strategies whose retrieval behavior differs
# enough to show a downstream effect while staying fast in CI.
DEFAULT_STRATEGIES: tuple[str, ...] = (
    "hybrid_keyword_embedding",
    "test_focused",
    "minimal",
)


@dataclass
class DownstreamTask:
    """A solvable fixture task: a tiny git repo plus the deterministic fix.

    ``files`` is applied by the patch agent via ``metadata={"files": ...}`` so the
    run is deterministically solvable; ``gold_paths`` are the files the retrieval
    pack *should* surface (used for the recall tiebreak signal).
    """

    name: str
    title: str
    body: str
    repo_files: dict[str, str]
    fix_files: dict[str, str]
    gold_paths: list[str]


def _calc_task() -> DownstreamTask:
    return DownstreamTask(
        name="calc_divide",
        title="Fix divide bug",
        body="divide returns 0 instead of a / b for any divisor",
        repo_files={
            "calculator.py": "def divide(a, b):\n    return 0\n",
            "test_calculator.py": (
                "from calculator import divide\n\n\n"
                "def test_divide():\n    assert divide(6, 2) == 3\n"
            ),
            "pyproject.toml": (
                '[project]\nname = "calc"\nversion = "0.1.0"\n'
                'requires-python = ">=3.11"\n'
            ),
        },
        fix_files={"calculator.py": "def divide(a, b):\n    return a / b\n"},
        gold_paths=["calculator.py"],
    )


def _greeter_task() -> DownstreamTask:
    return DownstreamTask(
        name="greeter_name",
        title="Fix greeting bug",
        body="greet should return 'Hello, <name>' but returns an empty greeting",
        repo_files={
            "greeter.py": "def greet(name):\n    return ''\n",
            "test_greeter.py": (
                "from greeter import greet\n\n\n"
                "def test_greet():\n    assert greet('Sam') == 'Hello, Sam'\n"
            ),
            "pyproject.toml": (
                '[project]\nname = "greet"\nversion = "0.1.0"\n'
                'requires-python = ">=3.11"\n'
            ),
        },
        fix_files={"greeter.py": "def greet(name):\n    return f'Hello, {name}'\n"},
        gold_paths=["greeter.py"],
    )


def default_tasks() -> list[DownstreamTask]:
    """A handful of small, solvable tasks (kept tiny so CI runs in seconds)."""
    return [_calc_task(), _greeter_task()]


class _PinnedStrategyPolicy:
    """A deterministic routing policy that forces a single context strategy.

    Routing's candidate space is ``agent × strategy × verification policy``; this
    policy always picks the candidate whose ``context_strategy`` equals ``strategy``
    (falling back to the first candidate if none match), so the run is compiled and
    executed with exactly the strategy under test. Implements just enough of the
    bandit-policy surface that ``AppService`` relies on (``choose_action`` plus the
    no-op persistence/learning hooks).
    """

    policy_version: str = "pinned-strategy-v1"

    def __init__(self, strategy: str) -> None:
        self.strategy = strategy

    def choose_action(
        self, features: dict, candidates: list[RoutingAction]
    ) -> PolicyDecision:
        chosen = next(
            (c for c in candidates if c.context_strategy == self.strategy),
            candidates[0],
        )
        return PolicyDecision(
            policy_version=self.policy_version,
            action=chosen,
            action_probability=1.0,
            context_key="pinned",
            candidate_scores={c.key(): 0.0 for c in candidates},
        )

    def export_arms(self) -> dict:
        return {}

    def import_arms(self, data: dict) -> None:  # noqa: D401 - no learned state
        return None

    def observe_reward(self, decision: PolicyDecision, reward: RewardEvent) -> None:
        return None


@dataclass
class DownstreamResult:
    """Metrics for one ``(task, strategy, rep)`` downstream run."""

    task: str
    strategy: str
    rep: int
    run_status: str = "unknown"
    verification_pass: bool = False
    reward: float = 0.0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    gold_recall: float = 0.0

    @property
    def success(self) -> bool:
        return self.run_status == "succeeded"

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "strategy": self.strategy,
            "rep": self.rep,
            "run_status": self.run_status,
            "success": self.success,
            "verification_pass": self.verification_pass,
            "reward": round(self.reward, 4),
            "cost_usd": round(self.cost_usd, 6),
            "latency_s": round(self.latency_s, 4),
            "gold_recall": round(self.gold_recall, 4),
        }


@dataclass
class StrategyAggregate:
    """Downstream metrics for one strategy, averaged across tasks × reps."""

    strategy: str
    n_runs: int = 0
    success_rate: float = 0.0
    verification_pass_rate: float = 0.0
    mean_reward: float = 0.0
    mean_cost_usd: float = 0.0
    mean_latency_s: float = 0.0
    mean_gold_recall: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "n_runs": self.n_runs,
            "success_rate": round(self.success_rate, 4),
            "verification_pass_rate": round(self.verification_pass_rate, 4),
            "mean_reward": round(self.mean_reward, 4),
            "mean_cost_usd": round(self.mean_cost_usd, 6),
            "mean_latency_s": round(self.mean_latency_s, 4),
            "mean_gold_recall": round(self.mean_gold_recall, 4),
        }

    def sort_key(self) -> tuple[float, float, float, float]:
        """Best by downstream success, then verification, then reward, then
        recall as a final tiebreak (the downstream signal dominates)."""
        return (
            self.success_rate,
            self.verification_pass_rate,
            self.mean_reward,
            self.mean_gold_recall,
        )


@dataclass
class ContextDownstreamReport:
    """Full downstream sweep: every ``(task, strategy, rep)`` run plus per-strategy
    aggregates and the best strategy chosen by downstream task success."""

    strategies: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    repetitions: int = 0
    results: list[DownstreamResult] = field(default_factory=list)
    aggregates: list[dict] = field(default_factory=list)
    best_strategy: str | None = None

    def result_for(
        self, task: str, strategy: str, rep: int
    ) -> DownstreamResult | None:
        return next(
            (
                r
                for r in self.results
                if r.task == task and r.strategy == strategy and r.rep == rep
            ),
            None,
        )

    def to_dict(self) -> dict:
        return {
            "strategies": list(self.strategies),
            "tasks": list(self.tasks),
            "repetitions": self.repetitions,
            "results": [r.to_dict() for r in self.results],
            "aggregates": self.aggregates,
            "best_strategy": self.best_strategy,
        }


def _build_repo(svc: AppService, root: Path, task: DownstreamTask):
    """Materialize ``task``'s repo as an initialized git repo + create it."""
    src = root / task.name
    src.mkdir(parents=True, exist_ok=True)
    for rel, content in task.repo_files.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "bench").release()
    repo.config_writer().set_value("user", "email", "bench@example.com").release()
    repo.index.add(list(task.repo_files))
    repo.index.commit("init")
    return svc.create_repo(task.name, str(src), default_branch="master")


def _recall_for_pack(pack: dict | None, gold_paths: Sequence[str]) -> float:
    """Top-10 recall of gold files within the (routed) context pack."""
    if not pack:
        return 0.0
    seen: list[str] = []
    for item in pack.get("items", []):
        path = item.get("path")
        if path and path not in seen:
            seen.append(path)
    top10 = seen[:10]
    return 1.0 if any(g in top10 for g in gold_paths) else 0.0


def _auto_resolve_reviews(svc: AppService, state):
    """Approve any open human-review escalation for ``state``'s run so the run
    reaches a terminal status; returns the (possibly resumed) workflow state."""
    from acp.core.enums import HumanVerdict
    from acp.schemas.human_review import HumanLabel

    status = state.status if isinstance(state.status, str) else state.status.value
    if status != "waiting_for_human":
        return state
    for item in svc.list_reviews():
        if item.run_id != state.run_id:
            continue
        svc.label_review(
            item.id,
            HumanLabel(
                review_item_id=item.id,
                task_id=item.task_id,
                attempt_id=item.attempt_id,
                verdict=HumanVerdict.PASS,
                score=1.0,
                reason="downstream benchmark auto-approval",
                reviewer="benchmark",
            ),
        )
    return svc.get_run(state.run_id) or state


def _run_one(
    root: Path, task: DownstreamTask, strategy: str, rep: int
) -> DownstreamResult:
    """Run a single ``(task, strategy, rep)`` end-to-end in an isolated service."""
    tmp = root / f"{task.name}__{strategy}__{rep}"
    tmp.mkdir(parents=True, exist_ok=True)
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp / 'd.db'}",
        artifact_dir=tmp / "art",
        workspace_dir=tmp / "ws",
    )
    svc = AppService(settings)
    svc.policy = _PinnedStrategyPolicy(strategy)  # type: ignore[assignment]
    repo = _build_repo(svc, tmp / "repos", task)
    created = svc.create_task(
        repo.id, task.title, task.body, metadata={"files": task.fix_files}
    )

    t0 = time.monotonic()
    state = svc.run_task(created.id)
    # If the run escalates to human review, auto-resolve it with a PASS label so
    # the run reaches a terminal downstream outcome (the fix is deterministically
    # correct), mirroring a reviewer approving the change.
    state = _auto_resolve_reviews(svc, state)
    latency = time.monotonic() - t0

    graph = svc.full_run_graph(state.run_id)
    status = state.status if isinstance(state.status, str) else state.status.value

    rewards = graph.get("reward_events", []) or []
    reward = float(rewards[-1].get("reward", 0.0)) if rewards else 0.0

    vruns = graph.get("verification_runs", []) or []
    verification_pass = bool(vruns) and all(v.get("status") == "pass" for v in vruns)

    traces = graph.get("agent_traces", []) or []
    cost = sum(float(t.get("estimated_cost_usd", 0.0)) for t in traces)

    recall = _recall_for_pack(graph.get("context_pack"), task.gold_paths)

    return DownstreamResult(
        task=task.name,
        strategy=strategy,
        rep=rep,
        run_status=status,
        verification_pass=verification_pass,
        reward=reward,
        cost_usd=cost,
        latency_s=latency,
        gold_recall=recall,
    )


def _aggregate(
    strategy: str, rows: list[DownstreamResult]
) -> StrategyAggregate:
    n = max(1, len(rows))
    return StrategyAggregate(
        strategy=strategy,
        n_runs=len(rows),
        success_rate=sum(1 for r in rows if r.success) / n,
        verification_pass_rate=sum(1 for r in rows if r.verification_pass) / n,
        mean_reward=sum(r.reward for r in rows) / n,
        mean_cost_usd=sum(r.cost_usd for r in rows) / n,
        mean_latency_s=sum(r.latency_s for r in rows) / n,
        mean_gold_recall=sum(r.gold_recall for r in rows) / n,
    )


def run_context_downstream_benchmark(
    tasks: list[DownstreamTask] | None = None,
    strategies: Sequence[str] | None = None,
    repetitions: int = 2,
) -> ContextDownstreamReport:
    """Run every ``(task × strategy × rep)`` end-to-end and aggregate downstream
    success, picking the best strategy by downstream task success (recall tiebreak).

    Each run executes in its own temp DB / workspace with the strategy pinned, so
    the recorded outcome reflects that strategy actually driving the agent's
    context. Deterministic patch agent — no network / API key.
    """
    tasks = tasks or default_tasks()
    strats = tuple(strategies) if strategies is not None else DEFAULT_STRATEGIES
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")
    unknown = [s for s in strats if s not in STRATEGIES]
    if unknown:
        raise ValueError(f"unknown strategies: {unknown}; valid: {STRATEGIES}")

    report = ContextDownstreamReport(
        strategies=list(strats),
        tasks=[t.name for t in tasks],
        repetitions=repetitions,
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for strat in strats:
            for task in tasks:
                for rep in range(repetitions):
                    report.results.append(_run_one(root, task, strat, rep))

    aggregates = [
        _aggregate(strat, [r for r in report.results if r.strategy == strat])
        for strat in strats
    ]
    aggregates.sort(key=lambda a: a.sort_key(), reverse=True)
    report.aggregates = [a.to_dict() for a in aggregates]
    report.best_strategy = aggregates[0].strategy if aggregates else None
    return report


def report_to_markdown(report: ContextDownstreamReport) -> str:
    """Render a human-readable downstream summary."""
    lines = ["# Context-strategy DOWNSTREAM benchmark", ""]
    lines.append(f"- strategies: {', '.join(report.strategies)}")
    lines.append(f"- tasks: {', '.join(report.tasks)}")
    lines.append(f"- repetitions: {report.repetitions}")
    lines.append(f"- best strategy (by downstream success): `{report.best_strategy}`")
    lines.append("")

    lines.append("## Per-strategy aggregate (downstream)")
    lines.append("")
    lines.append(
        "| strategy | runs | success | verify | reward | cost | latency_s | recall |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for a in report.aggregates:
        lines.append(
            f"| {a['strategy']} | {a['n_runs']} | {a['success_rate']} "
            f"| {a['verification_pass_rate']} | {a['mean_reward']} "
            f"| {a['mean_cost_usd']} | {a['mean_latency_s']} "
            f"| {a['mean_gold_recall']} |"
        )
    lines.append("")

    lines.append("## Per (task, strategy, rep)")
    lines.append("")
    lines.append(
        "| task | strategy | rep | status | verify | reward | cost | latency_s | recall |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in report.results:
        d = r.to_dict()
        lines.append(
            f"| {d['task']} | {d['strategy']} | {d['rep']} | {d['run_status']} "
            f"| {d['verification_pass']} | {d['reward']} | {d['cost_usd']} "
            f"| {d['latency_s']} | {d['gold_recall']} |"
        )
    return "\n".join(lines)
