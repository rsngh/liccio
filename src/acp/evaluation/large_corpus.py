"""Large empirical corpus generator (Alpha 10, WS11).

Where :mod:`acp.evaluation.capability_campaign` builds a campaign sized to clear
a few dozen sufficiently sampled cells, this module scales the same deterministic
synthetic-bakeoff idea up to a *large* empirical corpus: hundreds of sufficiently
sampled capability cells plus a preference set of well over a thousand
winner/loser pairs. It is the offline substrate a learned router / reward model
would train and be evaluated against, with no network and no randomness.

The generator reuses :meth:`CapabilityMatrix.from_bakeoff_report` (one sub-report
per repo type, merged via :meth:`CapabilityMatrix.add_cell`) exactly like the
campaign, but over a wider grid and with higher repetition counts so the
sufficient-cell count clears the >500 target at the default config. On top of the
populated matrix it derives:

* a **preference-pair count** — for each ``(task_type, risk_level, repo_type)``
  task group, every ordered (winner, loser) pair of *distinct-success* cells is a
  preference observation, the raw material for pairwise reward-model training;
* an **OPE overlap estimate** — the fraction of cells that are sufficiently
  sampled, a crude proxy for how much of the action space an off-policy estimator
  could trust;
* **Pareto frontier sizes** — the non-dominated cell count per task group, via
  :func:`acp.routing.pareto.pareto_frontier` over ``(success↑, cost↓, latency↓,
  risk↓)``.

Everything is a pure function of the axes, so a given config reproduces the same
corpus bit-for-bit.
"""

from __future__ import annotations

from acp.evaluation.capability_campaign import _build_cells, campaign_summary
from acp.routing.capability_matrix import CapabilityCell, CapabilityMatrix
from acp.routing.pareto import cell_objective, pareto_frontier

# Default corpus axes — deliberately larger than the campaign defaults so the
# default run clears >500 sufficiently sampled cells and >1,000 preference pairs
# while staying pure-arithmetic (no I/O). The TEST uses a much smaller config.
DEFAULT_TASK_TYPES = (
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
DEFAULT_RISK_LEVELS = ("low", "medium", "high")
DEFAULT_REPO_TYPES = ("library", "service", "monorepo", "cli", "webapp")
DEFAULT_ADAPTERS = ("simple_llm", "harness_a", "harness_b", "harness_c")
DEFAULT_STRATEGIES = ("hybrid_keyword_embedding", "keyword_only")
DEFAULT_REPETITIONS = 8


def _build_matrix(
    *,
    task_types: tuple[str, ...] | list[str],
    risk_levels: tuple[str, ...] | list[str],
    repo_types: tuple[str, ...] | list[str],
    adapters: tuple[str, ...] | list[str],
    strategies: tuple[str, ...] | list[str],
    repetitions: int,
    seed_offset: int,
) -> CapabilityMatrix:
    """Populate one :class:`CapabilityMatrix` over the full corpus grid.

    Builds one bakeoff sub-report per repo type (a report keys to a single repo
    type) and merges every resulting cell into one matrix. Deterministic for a
    given set of axes and ``seed_offset``.
    """
    matrix = CapabilityMatrix()
    for repo_index, repo_type in enumerate(repo_types):
        report = {
            "cells": _build_cells(
                task_types=task_types,
                risk_levels=risk_levels,
                adapters=adapters,
                strategies=strategies,
                repetitions=repetitions,
                repo_index=repo_index,
                seed_offset=seed_offset,
            )
        }
        sub = CapabilityMatrix.from_bakeoff_report(report, repo_type=repo_type)
        for cell in sub.cells():
            matrix.add_cell(cell)
    return matrix


def _group_by_task(
    cells: list[CapabilityCell],
) -> dict[tuple[str, str, str], list[CapabilityCell]]:
    """Group sufficiently sampled cells by their (task_type, risk, repo) key."""
    groups: dict[tuple[str, str, str], list[CapabilityCell]] = {}
    for c in cells:
        if c.sufficient_data:
            groups.setdefault(c.task_key(), []).append(c)
    return groups


def count_preference_pairs(
    groups: dict[tuple[str, str, str], list[CapabilityCell]],
) -> int:
    """Count ordered (winner, loser) preference pairs derivable per task group.

    Within a ``(task_type, risk_level, repo_type)`` group a cell *wins* over
    another when it has the strictly higher ``success_rate`` — that ordered pair
    is one pairwise-preference observation. Ties (equal success) contribute no
    pair, since neither cell is preferred. The count is the raw size of the
    preference set a pairwise reward model would consume.
    """
    pairs = 0
    for cells in groups.values():
        for winner in cells:
            for loser in cells:
                if winner is loser:
                    continue
                if winner.success_rate > loser.success_rate:
                    pairs += 1
    return pairs


def pareto_frontier_sizes(
    groups: dict[tuple[str, str, str], list[CapabilityCell]],
    *,
    max_groups: int | None = None,
) -> dict[str, int]:
    """Non-dominated cell count per task group over (success, cost, latency, risk).

    Reuses :func:`acp.routing.pareto.pareto_frontier` with the shared
    :func:`cell_objective` key. ``max_groups`` (when set) samples the first N task
    groups in sorted-key order so a report stays compact; ``None`` covers all.
    """
    sizes: dict[str, int] = {}
    keys = sorted(groups)
    if max_groups is not None:
        keys = keys[:max_groups]
    for key in keys:
        frontier = pareto_frontier(groups[key], cell_objective)
        sizes["|".join(key)] = len(frontier)
    return sizes


def generate_large_corpus(
    *,
    task_types: tuple[str, ...] | list[str] = DEFAULT_TASK_TYPES,
    risk_levels: tuple[str, ...] | list[str] = DEFAULT_RISK_LEVELS,
    repo_types: tuple[str, ...] | list[str] = DEFAULT_REPO_TYPES,
    adapters: tuple[str, ...] | list[str] = DEFAULT_ADAPTERS,
    strategies: tuple[str, ...] | list[str] = DEFAULT_STRATEGIES,
    repetitions: int = DEFAULT_REPETITIONS,
    seed_offset: int = 0,
    max_frontier_groups: int | None = 25,
) -> dict:
    """Build a large deterministic bakeoff-style corpus and summarize it.

    Returns a JSON-serializable dict with:

    * ``n_cells`` — total capability cells in the populated matrix;
    * ``n_sufficient`` — cells clearing the sample floor (the >500 target at the
      default config);
    * ``n_preference_pairs`` — ordered (winner, loser) pairs across task groups
      (the >1,000 target at the default config);
    * ``ope_overlap_estimate`` — fraction of cells sufficiently sampled, a proxy
      for off-policy estimator overlap;
    * ``pareto_frontier_sizes`` — non-dominated cell count per (sampled) task
      group;
    * ``summary`` — the full :func:`campaign_summary` coverage report.

    The default config takes a few seconds (pure arithmetic); callers that need
    speed should pass a smaller grid / fewer repetitions.
    """
    matrix = _build_matrix(
        task_types=task_types,
        risk_levels=risk_levels,
        repo_types=repo_types,
        adapters=adapters,
        strategies=strategies,
        repetitions=repetitions,
        seed_offset=seed_offset,
    )
    cells = matrix.cells()
    n_cells = len(cells)
    n_sufficient = sum(1 for c in cells if c.sufficient_data)

    groups = _group_by_task(cells)
    n_preference_pairs = count_preference_pairs(groups)
    frontier_sizes = pareto_frontier_sizes(groups, max_groups=max_frontier_groups)
    ope_overlap_estimate = round(n_sufficient / n_cells, 6) if n_cells else 0.0

    summary = campaign_summary(matrix)
    return {
        "n_cells": n_cells,
        "n_sufficient": n_sufficient,
        "n_preference_pairs": n_preference_pairs,
        "ope_overlap_estimate": ope_overlap_estimate,
        "n_task_groups": len(groups),
        "pareto_frontier_sizes": frontier_sizes,
        "axes": {
            "task_types": list(task_types),
            "risk_levels": list(risk_levels),
            "repo_types": list(repo_types),
            "adapters": list(adapters),
            "strategies": list(strategies),
            "repetitions": repetitions,
        },
        "summary": summary,
    }


def corpus_headline(corpus: dict) -> str:
    """One-line human summary of a corpus dict (for runner stdout / logs)."""
    frontier = corpus["pareto_frontier_sizes"]
    total_frontier = sum(frontier.values())
    avg = round(total_frontier / len(frontier), 2) if frontier else 0.0
    return (
        f"n_cells={corpus['n_cells']} n_sufficient={corpus['n_sufficient']} "
        f"n_preference_pairs={corpus['n_preference_pairs']} "
        f"ope_overlap={corpus['ope_overlap_estimate']} "
        f"task_groups={corpus['n_task_groups']} "
        f"avg_frontier={avg}"
    )
