"""Integration tests for the storage & scale benchmark (Alpha 8, WS17).

Runs with tiny sizes so it stays fast (<20s). Asserts structure + finite,
recorded latencies + DB growth + a computed bool sub-quadratic verdict — never a
specific machine-dependent latency number.
"""

from __future__ import annotations

import math

from acp.evaluation.scale_benchmark import is_subquadratic, run_scale_benchmark

SIZES = [40, 80]


def test_run_scale_benchmark_structure() -> None:
    report = run_scale_benchmark(sizes=SIZES)

    assert report["sizes"] == SIZES
    assert len(report["per_n"]) == len(SIZES)

    for row, n in zip(report["per_n"], SIZES, strict=True):
        assert row["n"] == n
        assert row["total_entities"] > 0
        lat = row["latency_ms"]
        # every operation has a finite, non-negative latency recorded.
        for op in report["operations"]:
            assert op in lat
            assert math.isfinite(lat[op])
            assert lat[op] >= 0.0
        assert row["db_size_bytes"] > 0


def test_db_grows_with_n() -> None:
    report = run_scale_benchmark(sizes=SIZES)
    sizes = [row["db_size_bytes"] for row in report["per_n"]]
    # larger N must persist a larger DB.
    assert sizes[-1] > sizes[0]
    entities = [row["total_entities"] for row in report["per_n"]]
    assert entities[-1] > entities[0]


def test_subquadratic_verdict_is_bool() -> None:
    report = run_scale_benchmark(sizes=SIZES)
    assert isinstance(report["subquadratic"], bool)
    for op in report["operations"]:
        assert isinstance(report["subquadratic_by_operation"][op], bool)
    # On these tiny sizes nothing should look catastrophically super-quadratic.
    assert report["subquadratic"] is True


def test_is_subquadratic_heuristic() -> None:
    # linear growth (2x size -> 2x latency) is sub-quadratic.
    assert is_subquadratic([10, 20, 40], [10.0, 20.0, 40.0]) is True
    # quadratic growth (2x size -> 4x latency) is NOT sub-quadratic.
    assert is_subquadratic([10, 20, 40], [10.0, 40.0, 160.0]) is False
    # degenerate / insufficient data -> True (cannot claim super-quadratic).
    assert is_subquadratic([10], [5.0]) is True
