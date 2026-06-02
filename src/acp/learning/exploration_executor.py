"""Active-learning exploration executor (Alpha 9, WS9).

:mod:`acp.routing.exploration` answers *what to explore*: a
:class:`~acp.routing.exploration.CoverageGapAnalyzer` reads a capability matrix
and emits an :class:`~acp.routing.exploration.ExplorationPlan` of under-sampled
cells. That plan is a recommendation, not an action — it does not say which
concrete probes to run nor enforce an execution-time budget.

This module closes that gap. :class:`ExplorationTaskGenerator` turns a plan's
targets into concrete :class:`ExplorationTaskSpec` probes, honoring an
:class:`ExplorationBudgetPolicy` (sample/cost caps and an *allowed risk levels*
allowlist — e.g. only ``low``/``medium`` cells may be probed against live
traffic). :class:`ExplorationExecutor` then *simulates* running those probes by
synthesizing additional deterministic bakeoff cells for the targeted keys and
merging them into a **copy** of the matrix, so the caller can preview how much
sufficient-cell coverage the campaign would buy before spending anything.

Everything here is pure-python and deterministic; timestamps go through
:func:`acp.core.time.utcnow`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from acp.routing.capability_matrix import (
    MIN_SAMPLE,
    CapabilityMatrix,
)
from acp.routing.exploration import ExplorationPlan

# Default risk levels safe to probe against live traffic; higher tiers should be
# collected under a sandbox and are therefore filtered out of a live campaign.
DEFAULT_ALLOWED_RISK_LEVELS = ("low", "medium")


@dataclass
class ExplorationTaskSpec:
    """A concrete exploratory probe for one under-sampled cell.

    The first six fields are the cell key (mirroring
    :data:`~acp.routing.capability_matrix.KEY_FIELDS`); the remainder describe
    how many samples to collect, the policy/risk note carried over from the
    plan, and the estimated cost.
    """

    task_type: str
    risk_level: str
    repo_type: str
    adapter: str
    context_strategy: str
    verification_policy: str
    n_samples: int
    recommended_policy: str
    risk_note: str
    est_cost: float

    def key(self) -> tuple[str, ...]:
        """The six-field cell identity this probe targets."""
        return (
            self.task_type,
            self.risk_level,
            self.repo_type,
            self.adapter,
            self.context_strategy,
            self.verification_policy,
        )

    def key_str(self) -> str:
        return "|".join(self.key())

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "risk_level": self.risk_level,
            "repo_type": self.repo_type,
            "adapter": self.adapter,
            "context_strategy": self.context_strategy,
            "verification_policy": self.verification_policy,
            "n_samples": self.n_samples,
            "recommended_policy": self.recommended_policy,
            "risk_note": self.risk_note,
            "est_cost": round(self.est_cost, 6),
        }


@dataclass
class ExplorationBudgetPolicy:
    """Execution-time caps on an exploration campaign.

    Unlike :class:`~acp.routing.exploration.ExplorationBudget` (which shapes the
    *plan*), this policy gates *task generation*: targets whose ``risk_level`` is
    not in ``allowed_risk_levels`` are dropped, and the cumulative sample / cost
    caps stop emitting specs once they would be exceeded.
    """

    max_samples: int | None = None
    max_cost: float | None = None
    allowed_risk_levels: tuple[str, ...] = DEFAULT_ALLOWED_RISK_LEVELS

    def allows_risk(self, risk_level: str) -> bool:
        return risk_level in self.allowed_risk_levels

    def as_dict(self) -> dict:
        return {
            "max_samples": self.max_samples,
            "max_cost": self.max_cost,
            "allowed_risk_levels": list(self.allowed_risk_levels),
        }


class ExplorationTaskGenerator:
    """Turn an :class:`ExplorationPlan` into concrete, budget-bounded probes."""

    def generate(
        self,
        plan: ExplorationPlan,
        budget_policy: ExplorationBudgetPolicy | None = None,
    ) -> list[ExplorationTaskSpec]:
        """Emit one :class:`ExplorationTaskSpec` per allowed target.

        Targets are consumed in plan order (the plan already orders them
        most-ignorant first). A target is skipped when its risk level is not
        allowed by ``budget_policy``; the per-target ``n_samples`` is clamped so
        the running sample/cost totals never exceed the policy caps. Once a cap
        is exhausted, remaining targets are dropped.
        """
        policy = budget_policy or ExplorationBudgetPolicy()
        specs: list[ExplorationTaskSpec] = []
        used_samples = 0
        used_cost = 0.0
        for target in plan.targets:
            if not policy.allows_risk(target.risk_level):
                continue
            n = target.samples_needed
            if n <= 0:
                continue
            per_sample_cost = (
                target.est_cost / target.samples_needed
                if target.samples_needed
                else 0.0
            )
            if policy.max_samples is not None:
                remaining = policy.max_samples - used_samples
                if remaining <= 0:
                    break
                n = min(n, remaining)
            est_cost = round(n * per_sample_cost, 6)
            if policy.max_cost is not None and used_cost + est_cost > policy.max_cost + 1e-9:
                if per_sample_cost <= 0:
                    break
                affordable = int((policy.max_cost - used_cost) / per_sample_cost)
                if affordable <= 0:
                    break
                n = min(n, affordable)
                est_cost = round(n * per_sample_cost, 6)
            if n <= 0:
                continue
            specs.append(
                ExplorationTaskSpec(
                    task_type=target.task_type,
                    risk_level=target.risk_level,
                    repo_type=target.repo_type,
                    adapter=target.agent_class,
                    context_strategy=target.context_strategy,
                    verification_policy=target.verification_policy,
                    n_samples=n,
                    recommended_policy=target.recommended_policy,
                    risk_note=target.risk_note,
                    est_cost=est_cost,
                )
            )
            used_samples += n
            used_cost = round(used_cost + est_cost, 6)
        return specs


def _simulated_success_rate(spec: ExplorationTaskSpec) -> float:
    """Deterministic success rate for a synthesized probe, in ``[0.4, 0.95]``.

    Derived from a stable hash of the cell key so two runs on the same spec
    synthesize identical cells (no RNG, insertion-order independent). Kept above
    0.4 so the synthesized evidence is plausible rather than degenerate.
    """
    seed = sum(ord(c) for c in spec.key_str())
    return 0.4 + (seed % 56) / 100.0


class ExplorationExecutor:
    """Simulate running exploratory probes and measure coverage uplift."""

    def simulate(
        self,
        matrix: CapabilityMatrix,
        specs: list[ExplorationTaskSpec],
    ) -> dict:
        """Synthesize each spec's samples into a **copy** of ``matrix``.

        For every spec we build a small bakeoff sub-report (``n_samples`` run
        cells with a deterministic success rate) for the spec's exact key, fold
        it into a copy of the matrix accumulating onto any existing cell, and
        recompute the cell's sufficiency flags. The original matrix is never
        mutated. Returns ``{before, after, coverage_delta, specs_run}`` where the
        ``*_sufficient`` counts let the caller confirm exploration *increases*
        sufficient-cell coverage (``coverage_delta > 0``).
        """
        before_sufficient = sum(1 for c in matrix.cells() if c.sufficient_data)

        # Work on a copy so the caller's matrix is untouched.
        merged = CapabilityMatrix()
        for cell in matrix.cells():
            merged.add_cell(copy.deepcopy(cell))

        existing = {c.key(): c for c in merged.cells()}
        for spec in specs:
            rate = _simulated_success_rate(spec)
            report = {
                "cells": [
                    {
                        "task_type": spec.task_type,
                        "risk": spec.risk_level,
                        "adapter": spec.adapter,
                        "context_strategy": spec.context_strategy,
                        "verification_policy": spec.verification_policy,
                        "success": (i / spec.n_samples) < rate,
                    }
                    for i in range(spec.n_samples)
                ]
            }
            sub = CapabilityMatrix.from_bakeoff_report(
                report, repo_type=spec.repo_type
            )
            for new_cell in sub.cells():
                prior = existing.get(new_cell.key())
                if prior is not None:
                    total = prior.sample_size + new_cell.sample_size
                    prior.success_rate = round(
                        (
                            prior.success_rate * prior.sample_size
                            + new_cell.success_rate * new_cell.sample_size
                        )
                        / total,
                        4,
                    )
                    prior.sample_size = total
                    prior.last_updated = new_cell.last_updated
                    prior.recompute_flags()
                else:
                    new_cell.recompute_flags()
                    merged.add_cell(new_cell)
                    existing[new_cell.key()] = new_cell

        after_sufficient = sum(1 for c in merged.cells() if c.sufficient_data)
        return {
            "before": {"n_sufficient": before_sufficient, "min_sample": MIN_SAMPLE},
            "after": {"n_sufficient": after_sufficient, "min_sample": MIN_SAMPLE},
            "coverage_delta": after_sufficient - before_sufficient,
            "specs_run": len(specs),
        }


__all__ = [
    "DEFAULT_ALLOWED_RISK_LEVELS",
    "ExplorationBudgetPolicy",
    "ExplorationExecutor",
    "ExplorationTaskGenerator",
    "ExplorationTaskSpec",
]
