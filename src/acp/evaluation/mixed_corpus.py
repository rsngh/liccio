"""Larger mixed empirical corpus generator (Alpha 11, WS12).

Where :mod:`acp.evaluation.large_corpus` scales the deterministic synthetic
bakeoff up to *hundreds* of sufficiently sampled cells, this module mixes the
grid still wider — many task types x risk levels x **repo types** x adapters x
context strategies x repetitions — so the ``scale="full"`` config reaches the
Alpha-11 sizing target (thousands of tasks, 20 repo types, many sufficient
cells). It is the offline substrate a learned router / reward model would train
and be evaluated against, with no network and no randomness.

The generator reuses :func:`acp.evaluation.large_corpus._build_matrix` (one
bakeoff sub-report per repo type, merged into one matrix) over a wider grid, then
derives, on top of the populated matrix:

* **preference pairs** — within each ``(task_type, risk, repo)`` task group every
  ordered (winner, loser) distinct-success pair, the raw material for pairwise
  reward-model training (:func:`large_corpus.count_preference_pairs`);
* an **OPE overlap estimate** — the fraction of cells sufficiently sampled, a
  proxy for how much of the action space an off-policy estimator could trust;
* **Pareto frontier sizes** — non-dominated cell count per task group over
  ``(success, cost, latency, risk)``;
* a **mean counterfactual regret** — averaged over task groups, the success-rate
  gap between each cell and the best cell in its group, a self-contained analogue
  of :func:`acp.routing.counterfactual.total_regret`;
* a **drift-window count** — the number of (task_type, risk) slices the corpus
  spans, the unit a drift monitor would window over;
* **per-(task_type, risk) coverage** — sufficient / total cells per slice.

Everything is a pure function of the axes, so a given ``scale`` reproduces the
same statistics bit-for-bit (the only non-deterministic field is the wall-clock
timestamp on each matrix cell, which is not surfaced here).
"""

from __future__ import annotations

from collections import Counter

from acp.evaluation.large_corpus import (
    _build_matrix,
    _group_by_task,
    count_preference_pairs,
    pareto_frontier_sizes,
)
from acp.routing.capability_matrix import CapabilityCell

# Task / risk / adapter / strategy axes shared by both scales; only the repo-type
# breadth and repetition count grow with ``scale``.
TASK_TYPES = (
    "bugfix",
    "feature",
    "refactor",
    "test_gen",
    "docs",
    "dependency_bump",
    "perf",
    "security_fix",
    "migration",
    "lint_fix",
)
RISK_LEVELS = ("low", "medium", "high")
ADAPTERS = ("simple_llm", "harness_a", "harness_b", "harness_c")
STRATEGIES = ("hybrid_keyword_embedding", "keyword_only")

# 20 repo types for the full Alpha-11 sizing target; the test scale uses a
# two-repo slice so it stays tiny and fast.
FULL_REPO_TYPES = (
    "library",
    "service",
    "monorepo",
    "cli",
    "webapp",
    "fastapi_service",
    "react_ts_app",
    "db_migration_app",
    "security_auth_app",
    "flaky_ci_repo",
    "legacy_refactor_repo",
    "data_pipeline",
    "ml_training",
    "terraform_infra",
    "mobile_app",
    "go_service",
    "rust_crate",
    "java_service",
    "notebook_repo",
    "docs_site",
)

# Per-scale configuration. ``test`` is deliberately tiny (sub-second); ``full``
# reaches the Alpha-11 sizing (thousands of tasks, 20 repo types).
_SCALES: dict[str, dict] = {
    "test": {
        "task_types": ("bugfix", "feature", "refactor"),
        "risk_levels": ("low", "high"),
        "repo_types": ("library", "service"),
        "adapters": ("simple_llm", "harness_a"),
        "strategies": ("hybrid_keyword_embedding",),
        "repetitions": 6,
    },
    "full": {
        "task_types": TASK_TYPES,
        "risk_levels": RISK_LEVELS,
        "repo_types": FULL_REPO_TYPES,
        "adapters": ADAPTERS,
        "strategies": STRATEGIES,
        "repetitions": 8,
    },
}


def mean_counterfactual_regret(
    groups: dict[tuple[str, str, str], list[CapabilityCell]],
) -> float:
    """Mean per-cell success-rate gap to the best cell in its task group.

    For each ``(task_type, risk, repo)`` group the best attainable success rate
    is ``max(success_rate)``; a cell's regret is how far it falls short of that
    best arm. The reported value is the mean regret over every cell in every
    group — a self-contained analogue of
    :func:`acp.routing.counterfactual.total_regret` that needs no fitted reward
    model. Returns ``0.0`` for an empty corpus.
    """
    total = 0.0
    n = 0
    for cells in groups.values():
        best = max(c.success_rate for c in cells)
        for c in cells:
            total += max(0.0, best - c.success_rate)
            n += 1
    return round(total / n, 6) if n else 0.0


def _slice_coverage(cells: list[CapabilityCell]) -> dict[str, dict[str, int]]:
    """Sufficient / total cell counts per ``(task_type, risk)`` slice.

    Keys are ``"{task_type}|{risk_level}"`` so the mapping is JSON-serializable
    and stable in sorted order. Every slice the corpus spans is reported, even
    when none of its cells clear the sample floor.
    """
    total: Counter[str] = Counter()
    suff: Counter[str] = Counter()
    for c in cells:
        key = f"{c.task_type}|{c.risk_level}"
        total[key] += 1
        if c.sufficient_data:
            suff[key] += 1
    return {
        key: {"total": total[key], "sufficient": suff[key]}
        for key in sorted(total)
    }


def generate_mixed_corpus(
    *,
    scale: str = "test",
    seed_offset: int = 0,
    max_frontier_groups: int | None = 25,
) -> dict:
    """Build a wide mixed deterministic bakeoff corpus and summarize it.

    ``scale="full"`` targets the Alpha-11 sizing (thousands of tasks, 20 repo
    types, many sufficient cells); ``scale="test"`` is a tiny, sub-second slice
    used by the test suite. Returns a JSON-serializable dict with:

    * ``n_tasks`` — total capability cells in the populated matrix (one cell is
      one routing-tuple task aggregate);
    * ``n_cells`` — alias of ``n_tasks`` (matrix cell count), kept explicit;
    * ``n_sufficient`` — cells clearing the sample floor;
    * ``n_preference_pairs`` — ordered (winner, loser) pairs across task groups;
    * ``ope_overlap_estimate`` — fraction of cells sufficiently sampled;
    * ``pareto_frontier_sizes`` — non-dominated cell count per (sampled) group;
    * ``drift_window_count`` — number of ``(task_type, risk)`` slices spanned;
    * ``mean_counterfactual_regret`` — mean success gap to the per-group best;
    * ``per_task_risk_coverage`` — sufficient / total cells per ``(task, risk)``.

    Deterministic for a given ``scale`` / ``seed_offset``.
    """
    if scale not in _SCALES:
        raise ValueError(f"unknown scale {scale!r}; expected one of {sorted(_SCALES)}")
    cfg = _SCALES[scale]

    matrix = _build_matrix(
        task_types=cfg["task_types"],
        risk_levels=cfg["risk_levels"],
        repo_types=cfg["repo_types"],
        adapters=cfg["adapters"],
        strategies=cfg["strategies"],
        repetitions=cfg["repetitions"],
        seed_offset=seed_offset,
    )
    cells = matrix.cells()
    n_cells = len(cells)
    n_sufficient = sum(1 for c in cells if c.sufficient_data)

    groups = _group_by_task(cells)
    n_preference_pairs = count_preference_pairs(groups)
    frontier_sizes = pareto_frontier_sizes(groups, max_groups=max_frontier_groups)
    ope_overlap_estimate = round(n_sufficient / n_cells, 6) if n_cells else 0.0
    coverage = _slice_coverage(cells)

    return {
        "scale": scale,
        "n_tasks": n_cells,
        "n_cells": n_cells,
        "n_sufficient": n_sufficient,
        "n_task_groups": len(groups),
        "n_preference_pairs": n_preference_pairs,
        "ope_overlap_estimate": ope_overlap_estimate,
        "pareto_frontier_sizes": frontier_sizes,
        "drift_window_count": len(coverage),
        "mean_counterfactual_regret": mean_counterfactual_regret(groups),
        "per_task_risk_coverage": coverage,
        "axes": {
            "task_types": list(cfg["task_types"]),
            "risk_levels": list(cfg["risk_levels"]),
            "repo_types": list(cfg["repo_types"]),
            "adapters": list(cfg["adapters"]),
            "strategies": list(cfg["strategies"]),
            "repetitions": cfg["repetitions"],
        },
    }


def mixed_corpus_headline(corpus: dict) -> str:
    """One-line human summary of a mixed-corpus dict (for runner stdout / logs)."""
    return (
        f"scale={corpus['scale']} n_tasks={corpus['n_tasks']} "
        f"n_sufficient={corpus['n_sufficient']} "
        f"n_preference_pairs={corpus['n_preference_pairs']} "
        f"ope_overlap={corpus['ope_overlap_estimate']} "
        f"drift_windows={corpus['drift_window_count']} "
        f"mean_regret={corpus['mean_counterfactual_regret']}"
    )
