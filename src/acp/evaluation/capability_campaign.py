"""Capability matrix population campaign (Alpha 8, WS13).

The :class:`~acp.routing.capability_matrix.CapabilityMatrix` is only as useful as
its coverage: a cell with too few observations is flagged ``low_sample`` and
:meth:`~acp.routing.capability_matrix.CapabilityMatrix.best_for` refuses to
recommend it. Bootstrapping that matrix from real bakeoffs is slow, so this
module generates a large, *deterministic* synthetic no-patch-style bakeoff report
spanning many task types x risk levels x repo types x adapters x context
strategies x repetitions, feeds it into the matrix, and reports which cells
become sufficiently sampled.

The synthetic success signal is purely a function of indices — there is no
randomness — so the populated matrix is reproducible bit-for-bit. Per-cell
success rates vary by ``(task_type, adapter)`` via :func:`_base_rate`, so cells
genuinely differ rather than collapsing to one value.

``generate_campaign_report`` builds one sub-report per repo type (because
:meth:`CapabilityMatrix.from_bakeoff_report` keys an entire report to a single
``repo_type``) and merges them via :meth:`CapabilityMatrix.add_cell`.
``campaign_summary`` then describes coverage and embeds a
:class:`~acp.routing.exploration.ExplorationPlan` explaining the missing samples.
"""

from __future__ import annotations

from collections import Counter

from acp.routing.capability_matrix import CapabilityMatrix
from acp.routing.exploration import CoverageGapAnalyzer

# Default campaign axes — sized so the default run yields well over 30
# sufficiently sampled cells while staying fast (pure arithmetic, no I/O).
DEFAULT_TASK_TYPES = (
    "bugfix",
    "feature",
    "refactor",
    "test_gen",
    "docs",
    "dependency_bump",
)
DEFAULT_RISK_LEVELS = ("low", "medium", "high")
DEFAULT_REPO_TYPES = ("library", "service", "monorepo")
DEFAULT_ADAPTERS = ("simple_llm", "harness_a", "harness_b")
DEFAULT_STRATEGIES = ("hybrid_keyword_embedding", "keyword_only")
DEFAULT_REPETITIONS = 6


def _base_rate(task_type: str, adapter: str) -> float:
    """Deterministic per-(task_type, adapter) success rate in ``[0.2, 0.95]``.

    Derived from stable hashes of the two names so cells differ from one another
    yet never depend on insertion order or RNG state.
    """
    seed = sum(ord(c) for c in task_type) * 31 + sum(ord(c) for c in adapter) * 7
    return 0.2 + (seed % 76) / 100.0


def _is_harness(adapter: str) -> bool:
    return adapter.startswith("harness")


def _cell_repetitions(task_type: str, adapter: str, repetitions: int) -> int:
    """Per-(task_type, adapter) repetition count.

    To make the campaign realistic, some cells are deliberately left
    under-sampled: when ``(task_type, adapter)`` hashes into a sparse bucket the
    cell collects only a fraction of the runs, so it stays below
    :data:`~acp.routing.capability_matrix.MIN_SAMPLE` and is correctly flagged
    ``low_sample``. The choice is deterministic (index-derived, no RNG).
    """
    bucket = (sum(ord(c) for c in task_type) + sum(ord(c) for c in adapter)) % 4
    if bucket == 0:
        return max(1, repetitions // 3)  # sparse: under-sampled
    return repetitions


def _build_cells(
    *,
    task_types: tuple[str, ...] | list[str],
    risk_levels: tuple[str, ...] | list[str],
    adapters: tuple[str, ...] | list[str],
    strategies: tuple[str, ...] | list[str],
    repetitions: int,
    repo_index: int,
    seed_offset: int,
) -> list[dict]:
    """Synthetic per-(task, adapter, run) cells for one repo type's sub-report.

    ``success`` is decided by ``(i / repetitions) < base_rate`` so the count of
    successes is a deterministic function of the base rate and repetition count.
    Cost/latency vary mildly by adapter to keep ranking meaningful.
    """
    cells: list[dict] = []
    for task_type in task_types:
        for risk in risk_levels:
            for adapter in adapters:
                rate = _base_rate(task_type, adapter)
                harness = _is_harness(adapter)
                reps = _cell_repetitions(task_type, adapter, repetitions)
                for strategy in strategies:
                    for i in range(reps):
                        success = (i / reps) < rate
                        # deterministic, index-derived spread for cost/latency
                        spread = ((seed_offset + repo_index + i) % 5) / 100.0
                        cells.append(
                            {
                                "task_type": task_type,
                                "risk": risk,
                                "adapter": adapter,
                                "is_harness": harness,
                                "context_strategy": strategy,
                                "success": success,
                                "cost_usd": round(
                                    (0.02 if harness else 0.01) + spread, 6
                                ),
                                "latency_s": round(
                                    (1.5 if harness else 1.0) + spread, 4
                                ),
                                "human_review_required": risk == "high"
                                and not success,
                            }
                        )
    return cells


def generate_campaign_report(
    *,
    task_types: tuple[str, ...] | list[str] = DEFAULT_TASK_TYPES,
    risk_levels: tuple[str, ...] | list[str] = DEFAULT_RISK_LEVELS,
    repo_types: tuple[str, ...] | list[str] = DEFAULT_REPO_TYPES,
    adapters: tuple[str, ...] | list[str] = DEFAULT_ADAPTERS,
    strategies: tuple[str, ...] | list[str] = DEFAULT_STRATEGIES,
    repetitions: int = DEFAULT_REPETITIONS,
    seed_offset: int = 0,
) -> CapabilityMatrix:
    """Build a populated :class:`CapabilityMatrix` from a synthetic campaign.

    One sub-report is built per ``repo_type`` (since a bakeoff report maps to a
    single repo type) and the resulting cells are merged into one matrix via
    :meth:`CapabilityMatrix.add_cell`. The result is fully deterministic for a
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


def campaign_summary(matrix: CapabilityMatrix) -> dict:
    """JSON-serializable coverage summary for a populated matrix.

    Reports the total cell count, the number of sufficiently sampled cells,
    per-task-type coverage (sufficient / total), and an embedded
    :class:`~acp.routing.exploration.ExplorationPlan` explaining which cells are
    still under-sampled. The plan is empty when every cell is sufficient.
    """
    cells = matrix.cells()
    n_cells = len(cells)
    n_sufficient = sum(1 for c in cells if c.sufficient_data)

    per_task: dict[str, dict[str, int]] = {}
    total_by_task: Counter[str] = Counter()
    suff_by_task: Counter[str] = Counter()
    for c in cells:
        total_by_task[c.task_type] += 1
        if c.sufficient_data:
            suff_by_task[c.task_type] += 1
    for task_type in total_by_task:
        per_task[task_type] = {
            "total": total_by_task[task_type],
            "sufficient": suff_by_task[task_type],
        }

    plan = CoverageGapAnalyzer().analyze(matrix)
    return {
        "n_cells": n_cells,
        "n_sufficient": n_sufficient,
        "n_under_sampled": n_cells - n_sufficient,
        "per_task_type": per_task,
        "exploration_plan": plan.to_dict(),
    }
