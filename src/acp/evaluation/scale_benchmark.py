"""Storage & scale benchmark (Alpha 8, WS17).

Seeds a fresh temp DB with synthetic entities at several sizes N and times the
core read/aggregate workflows (trace listing, exhaust-bundle build, capability
matrix, OPE-sample build, a representative ``list_by`` query) as N grows. The
report records per-N latencies + on-disk DB/artifact size and a simple
sub-quadratic verdict so regressions toward O(N^2) behavior are caught.

Pure-python, no network. Everything runs against temp dirs; nothing is mutated
in the caller's environment.
"""

from __future__ import annotations

import math
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import AgentKind, RiskLevel, TaskType, WeakLabelValue
from acp.db.repositories import EntityStore
from acp.db.session import session_scope
from acp.schemas.context import ContextItem
from acp.schemas.evaluation import EvaluationResult, WeakLabel
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction, RoutingDecision
from acp.schemas.task import Task
from acp.schemas.trace import AgentTrace


def seed_synthetic_db(
    service: AppService,
    *,
    n_tasks: int = 100,
    n_traces: int | None = None,
    n_context_items: int | None = None,
    repo_id: str = "repo_synthetic",
) -> dict[str, int]:
    """Bulk-insert synthetic entities into ``service``'s DB.

    For each synthetic task we also insert one AgentTrace, one RoutingDecision,
    one RewardEvent and one EvaluationResult (so the OPE/exhaust workflows have
    real rows to chew through), plus a configurable number of standalone
    ContextItems. All inserts happen inside a single ``session_scope`` so seeding
    stays roughly O(N) and fast.

    ``n_traces`` / ``n_context_items`` default to ``n_tasks`` when ``None``.
    Returns a count of each entity type inserted.
    """
    n_traces = n_tasks if n_traces is None else n_traces
    n_context_items = n_tasks if n_context_items is None else n_context_items

    action = RoutingAction(agent_kind=AgentKind.FAKE, agent_name="fake")
    counts = {
        "tasks": 0, "traces": 0, "routing_decisions": 0,
        "rewards": 0, "evaluations": 0, "context_items": 0,
    }
    with session_scope(service.sessions) as s:
        es = EntityStore(s)
        for i in range(n_tasks):
            task = Task(
                id=f"task_syn_{i:07d}", repo_id=repo_id,
                title=f"synthetic task {i}", body="bulk-inserted scale fixture",
                task_type=TaskType.BUGFIX, risk_level=RiskLevel.MEDIUM,
            )
            es.save(task)
            counts["tasks"] += 1

            attempt_id = f"attempt_syn_{i:07d}"
            if i < n_traces:
                es.save(AgentTrace(
                    id=f"atrace_syn_{i:07d}", attempt_id=attempt_id, task_id=task.id,
                    adapter_name="fake", status="completed", tool_calls=3,
                    changed_files=["a.py"], diff_lines=10,
                ))
                counts["traces"] += 1

            decision = RoutingDecision(
                id=f"route_syn_{i:07d}", task_id=task.id, policy_version="v1",
                action=action, action_probability=0.5, candidate_actions=[action],
                feature_hash=f"{TaskType.BUGFIX.value}|{RiskLevel.MEDIUM.value}",
            )
            es.save(decision)
            counts["routing_decisions"] += 1

            es.save(RewardEvent(
                id=f"reward_syn_{i:07d}", task_id=task.id, attempt_id=attempt_id,
                routing_decision_id=decision.id, reward=1.0 if i % 2 == 0 else 0.0,
                components={"objective": 1.0 if i % 2 == 0 else 0.0},
            ))
            counts["rewards"] += 1

            es.save(EvaluationResult(
                id=f"eval_syn_{i:07d}", task_id=task.id, attempt_id=attempt_id,
                spec_compliance=0.8, confidence=0.7,
            ))
            counts["evaluations"] += 1

            es.save(WeakLabel(
                id=f"weak_syn_{i:07d}", task_id=task.id, attempt_id=attempt_id,
                label=WeakLabelValue.SUCCESS, confidence=0.6,
                probabilities={"success": 0.6},
            ))

        for j in range(n_context_items):
            es.save(ContextItem(
                id=f"citem_syn_{j:07d}", kind="file_chunk", path=f"src/mod_{j}.py",
                content=f"# synthetic chunk {j}\n", token_estimate=8,
            ), extra_index={"pack_id": f"pack_syn_{j % max(1, n_tasks):07d}"})
            counts["context_items"] += 1
    return counts


def _dir_size_bytes(path: Path) -> int:
    """Total size of all files under ``path`` (0 if it does not exist)."""
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _time_ms(fn: Callable[[], Any]) -> tuple[float, Any]:
    """Run ``fn`` and return (elapsed_ms, result)."""
    start = time.perf_counter()
    result = fn()
    return (time.perf_counter() - start) * 1000.0, result


def is_subquadratic(
    sizes: list[int], latencies: list[float], *, max_ratio: float = 3.5
) -> bool:
    """Heuristic check that ``latencies`` grow slower than ~O(N^2) in ``sizes``.

    Idea: for true quadratic cost, *doubling* N multiplies latency by ~4x; linear
    cost gives ~2x. For each adjacent (smaller, larger) size pair we extrapolate
    the observed latency ratio to a per-doubling basis (so a 2x step and a 4x step
    are comparable): ``ratio_per_double = (l1/l0) ** (ln2 / ln(size_ratio))``. We
    then require the *worst* per-doubling growth to stay under ``max_ratio``
    (default 3.5, i.e. clearly below the ~4x expected for quadratic). Pairs whose
    latencies are both sub-millisecond are ignored so timer noise on cheap
    operations does not produce false alarms.
    """
    if len(sizes) < 2 or len(sizes) != len(latencies):
        return True  # not enough data to claim super-quadratic growth
    paired = sorted(zip(sizes, latencies, strict=True), key=lambda p: p[0])
    worst = 0.0
    for (n0, l0), (n1, l1) in zip(paired, paired[1:], strict=False):
        if n1 <= n0 or l0 <= 0.0:
            continue
        # ignore sub-millisecond noise that can dwarf real growth.
        if l1 < 1.0 and l0 < 1.0:
            continue
        size_ratio = n1 / n0
        exponent = math.log(2.0) / math.log(size_ratio)
        ratio_per_double = (l1 / l0) ** exponent
        worst = max(worst, ratio_per_double)
    return worst < max_ratio


def run_scale_benchmark(
    sizes: list[int] | None = None,
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Seed a fresh temp DB per N and time the core storage workflows.

    For each N in ``sizes`` a brand-new ``AppService`` (isolated temp sqlite DB +
    artifact/workspace dirs) is seeded with ~N entities, then we time:
      * trace listing            — ``EntityStore.list_by(AgentTrace)``
      * exhaust-bundle build     — ``service.build_exhaust_bundle()``
      * capability-matrix build  — ``service.build_capability_matrix()``
      * OPE-sample build         — ``service._ope_samples()``
      * representative list_by   — ``EntityStore.list_by(Task)``

    Returns a JSON-serializable report: per-N latencies + db/artifact size, and a
    per-operation sub-quadratic verdict plus an overall verdict.
    """
    sizes = sizes or [50, 100, 200]
    root = Path(base_dir) if base_dir is not None else Path(tempfile.mkdtemp(prefix="acp_scale_"))
    root.mkdir(parents=True, exist_ok=True)

    op_names = ["list_traces", "build_exhaust_bundle", "build_capability_matrix",
                "ope_samples", "list_tasks"]
    per_n: list[dict[str, Any]] = []

    for n in sorted(sizes):
        tmp = root / f"n_{n}"
        db_path = tmp / "s.db"
        art_dir = tmp / "art"
        ws_dir = tmp / "ws"
        for d in (art_dir, ws_dir):
            d.mkdir(parents=True, exist_ok=True)
        service = AppService(ACPSettings(
            database_url=f"sqlite+aiosqlite:///{db_path}",
            artifact_dir=art_dir, workspace_dir=ws_dir,
        ))
        counts = seed_synthetic_db(service, n_tasks=n)

        latencies: dict[str, float] = {}
        with session_scope(service.sessions) as s:
            es = EntityStore(s)
            store = es
            latencies["list_traces"], _ = _time_ms(lambda: store.list_by(AgentTrace))  # noqa: B023
            latencies["list_tasks"], _ = _time_ms(lambda: store.list_by(Task))  # noqa: B023
        latencies["build_exhaust_bundle"], _ = _time_ms(service.build_exhaust_bundle)
        latencies["build_capability_matrix"], _ = _time_ms(service.build_capability_matrix)
        latencies["ope_samples"], _ = _time_ms(service._ope_samples)

        service.engine.dispose()
        per_n.append({
            "n": n,
            "entity_counts": counts,
            "total_entities": sum(counts.values()),
            "latency_ms": {k: round(v, 4) for k, v in latencies.items()},
            "db_size_bytes": _dir_size_bytes(tmp) if db_path.exists() else 0,
            "artifact_size_bytes": _dir_size_bytes(art_dir),
        })

    verdicts: dict[str, bool] = {}
    ordered_sizes = [row["n"] for row in per_n]
    for op in op_names:
        lats = [float(row["latency_ms"][op]) for row in per_n]
        verdicts[op] = is_subquadratic(ordered_sizes, lats)

    return {
        "sizes": ordered_sizes,
        "operations": op_names,
        "per_n": per_n,
        "subquadratic_by_operation": verdicts,
        "subquadratic": all(verdicts.values()),
        "heuristic": (
            "Per adjacent (smaller,larger) size pair, extrapolate the latency "
            "ratio to a per-doubling basis (ln2/ln(size_ratio) exponent) and "
            "require the worst per-doubling growth < 3.5 (linear ~2x, quadratic "
            "~4x); sub-millisecond timings are ignored as noise."
        ),
    }
