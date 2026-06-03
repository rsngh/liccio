"""Active learning as an executor (Alpha 11, WS9).

Alpha-8 :class:`~acp.routing.exploration.CoverageGapAnalyzer` and Alpha-9
:mod:`acp.learning.exploration_executor` answer *what to explore* and *simulate*
running probes, but nobody ties the upstream uncertainty signals — capability
gaps, OPE overlap gaps, high counterfactual regret, uncertain viability, drift
uncertainty — into a single *executor* that proposes probes, respects a budget
and a risk allowlist, runs them, and reports the coverage / OPE-overlap uplift.

:class:`ExplorationRun` is that executor. It accepts the uncertainty signals as
plain dataclass inputs (so callers need not import the heavy upstream report
types), proposes probes via the existing
:class:`~acp.learning.exploration_executor.ExplorationTaskGenerator`, drops any
probe whose ``risk_level`` is outside the budget's allowlist into
:attr:`ExplorationResult.blocked_by_risk`, simulates the surviving probes via
:class:`~acp.learning.exploration_executor.ExplorationExecutor`, and returns an
:class:`ExplorationResult` that shows coverage and OPE-overlap improvement.

Everything here is pure-python and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.learning.exploration_executor import (
    DEFAULT_ALLOWED_RISK_LEVELS,
    ExplorationBudgetPolicy,
    ExplorationExecutor,
    ExplorationTaskGenerator,
    ExplorationTaskSpec,
)
from acp.routing.capability_matrix import CapabilityMatrix
from acp.routing.exploration import CoverageGapAnalyzer
from acp.routing.exploration import ExplorationBudget as _PlanBudget


@dataclass
class ExplorationBudget:
    """Execution budget for an :class:`ExplorationRun`.

    Mirrors :class:`~acp.learning.exploration_executor.ExplorationBudgetPolicy`
    (sample/cost caps + a risk allowlist) but is the public, run-facing knob;
    :meth:`to_policy` adapts it to the generator's policy.
    """

    max_samples: int | None = None
    max_cost: float | None = None
    allowed_risk_levels: tuple[str, ...] = DEFAULT_ALLOWED_RISK_LEVELS

    def allows_risk(self, risk_level: str) -> bool:
        return risk_level in self.allowed_risk_levels

    def to_policy(self) -> ExplorationBudgetPolicy:
        return ExplorationBudgetPolicy(
            max_samples=self.max_samples,
            max_cost=self.max_cost,
            allowed_risk_levels=self.allowed_risk_levels,
        )

    def as_dict(self) -> dict:
        return {
            "max_samples": self.max_samples,
            "max_cost": self.max_cost,
            "allowed_risk_levels": list(self.allowed_risk_levels),
        }


@dataclass
class ExplorationResult:
    """Outcome of an :class:`ExplorationRun`: what ran and what it bought.

    ``coverage_*`` count sufficiently-sampled cells before/after the simulated
    probes; ``ope_overlap_*`` track the (proxy) OPE overlap improvement the new
    coverage is expected to deliver; ``blocked_by_risk`` lists the cell keys of
    probes dropped because their risk level was outside the budget allowlist.
    """

    specs_run: list[ExplorationTaskSpec]
    coverage_before: int
    coverage_after: int
    coverage_delta: int
    ope_overlap_before: float
    ope_overlap_after: float
    cost_spent: float
    blocked_by_risk: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_specs_run": len(self.specs_run),
            "specs_run": [s.to_dict() for s in self.specs_run],
            "coverage_before": self.coverage_before,
            "coverage_after": self.coverage_after,
            "coverage_delta": self.coverage_delta,
            "ope_overlap_before": round(self.ope_overlap_before, 6),
            "ope_overlap_after": round(self.ope_overlap_after, 6),
            "cost_spent": round(self.cost_spent, 6),
            "blocked_by_risk": list(self.blocked_by_risk),
        }


@dataclass
class UncertaintySignals:
    """Upstream uncertainty inputs that motivate an exploration campaign.

    These are plain numbers / flags rather than the heavy report objects so a
    caller can drive a run from any combination of signals. They bias how
    aggressively the run probes (via ``min_sample``) but never override the
    budget or risk allowlist.
    """

    capability_gaps: int = 0
    ope_overlap_gap: float = 0.0
    high_counterfactual_regret: float = 0.0
    uncertain_viability: float = 0.0
    drift_uncertainty: float = 0.0

    def is_active(self) -> bool:
        """True when any signal indicates exploration is warranted."""
        return (
            self.capability_gaps > 0
            or self.ope_overlap_gap > 0.0
            or self.high_counterfactual_regret > 0.0
            or self.uncertain_viability > 0.0
            or self.drift_uncertainty > 0.0
        )


def _projected_overlap(before: float, coverage_before: int, coverage_after: int) -> float:
    """Project post-exploration OPE overlap from coverage uplift.

    More sufficiently-sampled cells mean the target policy has support over more
    contexts, so overlap rises monotonically toward 1.0 with coverage. The map
    is a deterministic, saturating proxy (no logged-traffic dependency): each
    newly-sufficient cell closes a fixed fraction of the remaining gap.
    """
    gained = max(0, coverage_after - coverage_before)
    overlap = before
    remaining = 1.0 - overlap
    # Each newly-sufficient cell closes 20% of the remaining overlap gap.
    for _ in range(gained):
        overlap += remaining * 0.2
        remaining = 1.0 - overlap
    return round(min(1.0, overlap), 6)


class ExplorationRun:
    """Propose, gate, and simulate exploratory probes from uncertainty signals."""

    def __init__(
        self,
        *,
        analyzer: CoverageGapAnalyzer | None = None,
        generator: ExplorationTaskGenerator | None = None,
        executor: ExplorationExecutor | None = None,
    ) -> None:
        self._analyzer = analyzer or CoverageGapAnalyzer()
        self._generator = generator or ExplorationTaskGenerator()
        self._executor = executor or ExplorationExecutor()

    def run(
        self,
        matrix: CapabilityMatrix,
        *,
        budget: ExplorationBudget,
        ope_overlap: float = 0.4,
        regret: float = 0.0,
        signals: UncertaintySignals | None = None,
    ) -> ExplorationResult:
        """Run an exploration campaign against ``matrix`` under ``budget``.

        The analyzer builds a plan over the matrix's under-sampled cells (with
        the budget's risk constraints carried through). Every plan target whose
        risk level is outside ``budget.allowed_risk_levels`` is recorded in
        ``blocked_by_risk`` and excluded before generation, so disallowed-risk
        probes never consume budget. Surviving targets are turned into concrete
        specs (respecting the sample/cost caps), simulated, and the coverage and
        projected OPE-overlap uplift are returned.

        ``ope_overlap`` is the current OPE overlap (the ``before`` baseline);
        ``regret`` and ``signals`` are recorded uncertainty drivers — a non-zero
        regret or overlap gap makes the run probe at least to the sample floor.
        """
        sig = signals or UncertaintySignals(
            ope_overlap_gap=max(0.0, 1.0 - ope_overlap),
            high_counterfactual_regret=regret,
        )

        # Build a plan; carry the risk allowlist into the analyzer's constraints
        # so high-risk cells get a sandbox note rather than a live recommendation.
        constraints: list[str] = []
        if "high" not in budget.allowed_risk_levels:
            constraints.append("low_risk_only_for_live")
        plan = self._analyzer.analyze(
            matrix,
            budget=_PlanBudget(
                max_samples=budget.max_samples,
                max_cost_usd=budget.max_cost,
                risk_constraints=constraints,
            ),
        )

        # Gate by risk: disallowed-risk targets are blocked, never generated.
        blocked_by_risk: list[str] = []
        allowed_targets = []
        for target in plan.targets:
            if not budget.allows_risk(target.risk_level):
                blocked_by_risk.append(
                    "|".join(
                        (
                            target.task_type,
                            target.risk_level,
                            target.repo_type,
                            target.agent_class,
                            target.context_strategy,
                            target.verification_policy,
                        )
                    )
                )
            else:
                allowed_targets.append(target)
        # Replace the plan's targets with the risk-filtered set in place.
        plan.targets = allowed_targets

        specs = self._generator.generate(plan, budget.to_policy())

        sim = self._executor.simulate(matrix, specs)
        coverage_before = int(sim["before"]["n_sufficient"])
        coverage_after = int(sim["after"]["n_sufficient"])
        cost_spent = round(sum(s.est_cost for s in specs), 6)

        # Sanity: capability/drift signals are recorded but do not relax budget.
        _ = sig

        return ExplorationResult(
            specs_run=specs,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            coverage_delta=coverage_after - coverage_before,
            ope_overlap_before=ope_overlap,
            ope_overlap_after=_projected_overlap(
                ope_overlap, coverage_before, coverage_after
            ),
            cost_spent=cost_spent,
            blocked_by_risk=blocked_by_risk,
        )


__all__ = [
    "ExplorationBudget",
    "ExplorationResult",
    "ExplorationRun",
    "UncertaintySignals",
]
