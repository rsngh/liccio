"""Exploration policy designer (Alpha 8, WS12).

The capability matrix (:mod:`acp.routing.capability_matrix`) is honest about
ignorance: a routing cell whose ``sample_size`` is below
:data:`~acp.routing.capability_matrix.MIN_SAMPLE` is flagged ``low_sample`` and
:meth:`~acp.routing.capability_matrix.CapabilityMatrix.best_for` refuses to
recommend it. That refusal is correct but inert — it tells us *that* we are
uncertain, not *what to do about it*.

This module closes that loop. :class:`CoverageGapAnalyzer` reads the matrix,
finds the under-sampled cells, and emits a concrete :class:`ExplorationPlan`:
which cells need more samples, how many more, which policy should go collect
them, what that will cost, and what risk constraints apply (e.g. only explore a
live high-risk cell under sandboxed execution). The plan respects an optional
:class:`ExplorationBudget` so the recommendation never asks for more samples or
spend than allowed. Timestamps use :func:`acp.core.time.utcnow`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.core.time import isoformat, utcnow
from acp.routing.capability_matrix import (
    DEFAULT_AGENT_CLASS,
    MIN_SAMPLE,
    CapabilityCell,
    CapabilityMatrix,
)


@dataclass
class ExplorationBudget:
    """Caps on an exploration campaign.

    ``risk_constraints`` is a free-form list of policy tokens (e.g.
    ``"low_risk_only_for_live"``) the analyzer honors when deciding how to probe
    a cell — high-risk cells get a sandbox note rather than live traffic.
    """

    max_samples: int | None = None
    max_cost_usd: float | None = None
    risk_constraints: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "max_samples": self.max_samples,
            "max_cost_usd": self.max_cost_usd,
            "risk_constraints": self.risk_constraints,
        }


@dataclass
class ExplorationTarget:
    """A single under-sampled cell and the prescription to fill its gap."""

    task_type: str
    risk_level: str
    repo_type: str
    agent_class: str
    context_strategy: str
    verification_policy: str
    current_sample_size: int
    samples_needed: int
    recommended_policy: str
    est_cost: float
    risk_note: str

    def as_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "risk_level": self.risk_level,
            "repo_type": self.repo_type,
            "agent_class": self.agent_class,
            "context_strategy": self.context_strategy,
            "verification_policy": self.verification_policy,
            "current_sample_size": self.current_sample_size,
            "samples_needed": self.samples_needed,
            "recommended_policy": self.recommended_policy,
            "est_cost": self.est_cost,
            "risk_note": self.risk_note,
        }

    # alias for consistency with other routing dataclasses' to_dict()
    to_dict = as_dict


@dataclass
class ExplorationPlan:
    """The full exploration prescription across all under-sampled cells."""

    targets: list[ExplorationTarget]
    total_samples: int
    total_est_cost: float
    summary: str
    generated_at: str = field(default_factory=lambda: isoformat(utcnow()))
    budget: ExplorationBudget | None = None

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "n_targets": len(self.targets),
            "total_samples": self.total_samples,
            "total_est_cost": round(self.total_est_cost, 6),
            "summary": self.summary,
            "budget": self.budget.as_dict() if self.budget else None,
            "targets": [t.to_dict() for t in self.targets],
        }


# Known agent classes never need an "explore which arm" recommendation — we just
# need more samples of that arm. An unknown/default agent class means the cell is
# genuinely unexplored, so the recommendation is the generic explore policy.
def _recommend_policy(cell: CapabilityCell) -> str:
    if cell.agent_class and cell.agent_class != DEFAULT_AGENT_CLASS:
        return f"explore:{cell.agent_class}"
    return "explore"


def _risk_note(cell: CapabilityCell, constraints: list[str]) -> str:
    high_risk = cell.risk_level in ("high", "critical")
    live_constrained = "low_risk_only_for_live" in constraints
    if high_risk and live_constrained:
        return "high-risk cell: collect under Docker/sandbox, not live traffic"
    if high_risk:
        return "high-risk cell: prefer sandboxed execution"
    return "low-risk: safe to collect under Docker"


class CoverageGapAnalyzer:
    """Turn a capability matrix's low-sample cells into an exploration plan."""

    def analyze(
        self,
        matrix: CapabilityMatrix,
        *,
        min_sample: int | None = None,
        per_sample_cost: float = 0.01,
        budget: ExplorationBudget | None = None,
    ) -> ExplorationPlan:
        """Build an :class:`ExplorationPlan` for the matrix's under-sampled cells.

        A cell is under-sampled when its ``sample_size`` is below ``min_sample``
        (defaulting to the matrix's :data:`MIN_SAMPLE`). For each such cell the
        analyzer computes ``samples_needed = min_sample - current``, recommends a
        policy, estimates cost at ``per_sample_cost`` each, and attaches a risk
        note. The optional ``budget`` caps the total sample count (and, if set,
        spend): targets are taken in ascending order of current coverage (the
        most ignorant cells first) until a cap is hit, after which later targets
        are dropped.
        """
        threshold = MIN_SAMPLE if min_sample is None else min_sample
        constraints = budget.risk_constraints if budget else []

        # Under-sampled cells, most-ignorant first (then a stable key tie-break).
        under = sorted(
            (c for c in matrix.cells() if c.sample_size < threshold),
            key=lambda c: (c.sample_size, c.key_str()),
        )

        targets: list[ExplorationTarget] = []
        total_samples = 0
        total_cost = 0.0
        for cell in under:
            needed = threshold - cell.sample_size
            if needed <= 0:
                continue
            if budget and budget.max_samples is not None:
                remaining = budget.max_samples - total_samples
                if remaining <= 0:
                    break
                needed = min(needed, remaining)
            est_cost = round(needed * per_sample_cost, 6)
            if (budget and budget.max_cost_usd is not None
                    and total_cost + est_cost > budget.max_cost_usd + 1e-9):
                affordable = int((budget.max_cost_usd - total_cost) / per_sample_cost)
                if affordable <= 0:
                    break
                needed = min(needed, affordable)
                est_cost = round(needed * per_sample_cost, 6)

            targets.append(ExplorationTarget(
                task_type=cell.task_type,
                risk_level=cell.risk_level,
                repo_type=cell.repo_type,
                agent_class=cell.agent_class,
                context_strategy=cell.context_strategy,
                verification_policy=cell.verification_policy,
                current_sample_size=cell.sample_size,
                samples_needed=needed,
                recommended_policy=_recommend_policy(cell),
                est_cost=est_cost,
                risk_note=_risk_note(cell, constraints),
            ))
            total_samples += needed
            total_cost = round(total_cost + est_cost, 6)

        summary = self._summarize(targets, total_samples, total_cost, threshold)
        return ExplorationPlan(
            targets=targets,
            total_samples=total_samples,
            total_est_cost=total_cost,
            summary=summary,
            budget=budget,
        )

    @staticmethod
    def _summarize(
        targets: list[ExplorationTarget],
        total_samples: int,
        total_cost: float,
        threshold: int,
    ) -> str:
        if not targets:
            return f"All cells meet the {threshold}-sample floor; no exploration needed."
        t = targets[0]
        head = (
            f"We cannot confidently choose for "
            f"{t.task_type}/{t.risk_level} on {t.repo_type}; need "
            f"{t.samples_needed} more {t.risk_level}-risk samples under Docker"
        )
        return (
            f"{head}. {len(targets)} under-sampled cell(s) below the "
            f"{threshold}-sample floor: {total_samples} samples total, "
            f"est ${total_cost:.4f}."
        )
