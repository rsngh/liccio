"""Integration tests for the large empirical corpus generator (Alpha 10, WS11).

Uses a SMALL config so the test stays fast (<15s). Asserts the corpus statistics
are computed (n_cells / n_sufficient), a non-empty preference set is derived, the
report is JSON-serializable, and small-scale coverage is reported — never a
machine- or scale-dependent absolute number.
"""

from __future__ import annotations

import json

from acp.evaluation.large_corpus import (
    corpus_headline,
    generate_large_corpus,
)

# Small but realistic grid: enough reps for some cells to clear the sample floor.
SMALL = {
    "task_types": ("bugfix", "feature", "refactor"),
    "risk_levels": ("low", "high"),
    "repo_types": ("library", "service"),
    "adapters": ("simple_llm", "harness_a"),
    "strategies": ("hybrid_keyword_embedding",),
    "repetitions": 6,
}


def test_large_corpus_statistics_computed() -> None:
    corpus = generate_large_corpus(**SMALL)

    assert corpus["n_cells"] > 0
    assert 0 <= corpus["n_sufficient"] <= corpus["n_cells"]
    # at this config some cells clear the floor, so a preference set exists.
    assert corpus["n_sufficient"] > 0
    assert corpus["n_preference_pairs"] > 0
    assert 0.0 <= corpus["ope_overlap_estimate"] <= 1.0


def test_large_corpus_coverage_reported() -> None:
    corpus = generate_large_corpus(**SMALL)

    summary = corpus["summary"]
    assert summary["n_cells"] == corpus["n_cells"]
    assert summary["n_sufficient"] == corpus["n_sufficient"]
    # per-task-type coverage is reported for every task type seeded.
    per_task = summary["per_task_type"]
    for task_type in SMALL["task_types"]:
        assert task_type in per_task
        assert per_task[task_type]["sufficient"] <= per_task[task_type]["total"]

    # frontier sizes are reported per (sampled) task group and are >= 1.
    frontier = corpus["pareto_frontier_sizes"]
    assert frontier  # non-empty given sufficient cells exist
    for size in frontier.values():
        assert size >= 1


def test_large_corpus_json_serializable_and_deterministic() -> None:
    a = generate_large_corpus(**SMALL)
    b = generate_large_corpus(**SMALL)

    # JSON-serializable.
    blob = json.dumps(a)
    assert isinstance(blob, str)
    # the derived statistics are deterministic for a given config (the only
    # non-deterministic fields are wall-clock timestamps inside the matrix cells).
    for key in (
        "n_cells",
        "n_sufficient",
        "n_preference_pairs",
        "ope_overlap_estimate",
        "n_task_groups",
        "pareto_frontier_sizes",
    ):
        assert a[key] == b[key]
    # headline is a non-empty string.
    assert corpus_headline(a)
