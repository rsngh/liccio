"""Storage & scale benchmark v2 (Alpha 10, WS17).

A wider sweep than :mod:`acp.evaluation.scale_benchmark`: it seeds the same
synthetic DB (via :func:`scale_benchmark.seed_synthetic_db`) at several sizes N
but times *more* control-plane operations as N grows, so a regression toward
O(N^2) is caught across the surfaces an operator actually touches:

  * ``list_eval_runs``        — run-graph-ish listing (model-dumped eval runs);
  * ``build_capability_matrix`` — capability-matrix build from persisted runs;
  * ``ope_samples``           — OPE-sample build from the decision/reward log;
  * ``build_training_dataset`` — dataset build (redact + leakage audit) to disk;
  * ``validate_artifact``     — JSON artifact validation of that dataset's report;
  * ``control_plane_health``  — health-snapshot aggregation across all entities.

Each operation gets its own per-doubling sub-quadratic verdict (reusing
:func:`scale_benchmark.is_subquadratic`) plus an overall verdict. Pure-python, no
network; every size runs against an isolated temp dir that is left untouched in
the caller's environment except under the chosen ``base_dir``.
"""

from __future__ import annotations

import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.time import isoformat, utcnow
from acp.evaluation.scale_benchmark import (
    _dir_size_bytes,
    is_subquadratic,
    seed_synthetic_db,
)
from acp.observability.artifact_manifest import validate_artifact

# The operations measured per N. Order is the report's column order.
OP_NAMES = (
    "list_eval_runs",
    "build_capability_matrix",
    "ope_samples",
    "build_training_dataset",
    "validate_artifact",
    "control_plane_health",
)


def _time_ms(fn: Callable[[], Any]) -> tuple[float, Any]:
    """Run ``fn`` and return (elapsed_ms, result)."""
    start = time.perf_counter()
    result = fn()
    return (time.perf_counter() - start) * 1000.0, result


def _measure_one(service: AppService, *, art_dir: Path) -> dict[str, float]:
    """Time every v2 operation once against a seeded ``service``.

    ``build_training_dataset`` writes a JSONL dataset under ``art_dir`` and a
    sibling report JSON, which ``validate_artifact`` then reads back and checks —
    so the two operations exercise the real write+validate round-trip.
    """
    latencies: dict[str, float] = {}

    latencies["list_eval_runs"], _ = _time_ms(service.list_eval_runs)
    latencies["build_capability_matrix"], _ = _time_ms(service.build_capability_matrix)
    latencies["ope_samples"], _ = _time_ms(service._ope_samples)

    dataset_path = art_dir / "routing_dataset.jsonl"
    report_path = art_dir / "routing_dataset_report.json"

    def _build_dataset() -> dict:
        result = service.build_training_dataset("routing", out=str(dataset_path))
        report_path.write_text(json.dumps(result, indent=2))
        return result

    latencies["build_training_dataset"], _ = _time_ms(_build_dataset)
    latencies["validate_artifact"], _ = _time_ms(
        lambda: validate_artifact(
            report_path.name, ["kind", "dataset_id", "n_examples"], art_dir
        )
    )
    latencies["control_plane_health"], _ = _time_ms(service.control_plane_health)
    return latencies


def run_scale_benchmark_v2(
    sizes: list[int] | None = None,
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Seed a fresh temp DB per N and time the v2 storage workflows.

    For each N in ``sizes`` a brand-new ``AppService`` (isolated temp sqlite DB +
    artifact/workspace dirs) is seeded with ~N entities via
    :func:`seed_synthetic_db`, then every operation in :data:`OP_NAMES` is timed
    once. Returns a JSON-serializable report: per-N latencies + db/artifact size,
    a per-operation sub-quadratic verdict, and an overall verdict.
    """
    sizes = sizes or [100, 200, 400]
    root = (
        Path(base_dir)
        if base_dir is not None
        else Path(tempfile.mkdtemp(prefix="acp_scale_v2_"))
    )
    root.mkdir(parents=True, exist_ok=True)

    per_n: list[dict[str, Any]] = []
    for n in sorted(sizes):
        tmp = root / f"n_{n}"
        db_path = tmp / "s.db"
        art_dir = tmp / "art"
        ws_dir = tmp / "ws"
        for d in (art_dir, ws_dir):
            d.mkdir(parents=True, exist_ok=True)
        service = AppService(
            ACPSettings(
                database_url=f"sqlite+aiosqlite:///{db_path}",
                artifact_dir=art_dir,
                workspace_dir=ws_dir,
            )
        )
        counts = seed_synthetic_db(service, n_tasks=n)
        latencies = _measure_one(service, art_dir=art_dir)
        service.engine.dispose()
        per_n.append(
            {
                "n": n,
                "entity_counts": counts,
                "total_entities": sum(counts.values()),
                "latency_ms": {k: round(v, 4) for k, v in latencies.items()},
                "db_size_bytes": _dir_size_bytes(tmp) if db_path.exists() else 0,
                "artifact_size_bytes": _dir_size_bytes(art_dir),
            }
        )

    ordered_sizes = [row["n"] for row in per_n]
    verdicts: dict[str, bool] = {}
    for op in OP_NAMES:
        lats = [float(row["latency_ms"][op]) for row in per_n]
        verdicts[op] = is_subquadratic(ordered_sizes, lats)

    return {
        "generated_at": isoformat(utcnow()),
        "sizes": ordered_sizes,
        "operations": list(OP_NAMES),
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
