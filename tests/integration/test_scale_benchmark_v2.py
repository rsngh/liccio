"""Integration tests for the storage & scale benchmark v2 (Alpha 10, WS17).

Runs with tiny sizes so it stays fast (<20s). Asserts structure + finite,
recorded latencies for the extra v2 operations + DB growth + a computed bool
sub-quadratic verdict — never a specific machine-dependent latency number.
"""

from __future__ import annotations

import math

from acp.evaluation.scale_benchmark_v2 import OP_NAMES, run_scale_benchmark_v2

SIZES = [40, 80]


def test_run_scale_benchmark_v2_structure() -> None:
    report = run_scale_benchmark_v2(sizes=SIZES)

    assert report["sizes"] == SIZES
    assert report["operations"] == list(OP_NAMES)
    assert len(report["per_n"]) == len(SIZES)

    for row, n in zip(report["per_n"], SIZES, strict=True):
        assert row["n"] == n
        assert row["total_entities"] > 0
        assert row["db_size_bytes"] > 0
        lat = row["latency_ms"]
        # every v2 operation has a finite, non-negative latency recorded.
        for op in OP_NAMES:
            assert op in lat
            assert math.isfinite(lat[op])
            assert lat[op] >= 0.0


def test_run_scale_benchmark_v2_extra_operations_present() -> None:
    report = run_scale_benchmark_v2(sizes=SIZES)

    # the v2 sweep measures more than v1 — these are the new surfaces.
    for op in (
        "list_eval_runs",
        "build_training_dataset",
        "validate_artifact",
        "control_plane_health",
    ):
        assert op in report["operations"]
        assert op in report["subquadratic_by_operation"]


def test_run_scale_benchmark_v2_subquadratic_verdict_is_bool() -> None:
    report = run_scale_benchmark_v2(sizes=SIZES)

    assert isinstance(report["subquadratic"], bool)
    for op in OP_NAMES:
        assert isinstance(report["subquadratic_by_operation"][op], bool)
