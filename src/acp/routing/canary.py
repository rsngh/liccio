"""Policy canary simulator (Alpha 8, WS10).

A passing promotion gate (:mod:`acp.routing.promotion`) hands back a
:class:`~acp.routing.promotion.PolicyCanaryPlan`: a staged traffic ramp
(``5/25/50/100%``) plus a set of guardrails. Shipping a policy is not a single
flip — traffic is shifted onto the candidate one stage at a time, and at each
stage the *observed* operational metrics are checked against the guardrails. The
first stage that breaches a guardrail rolls the rollout back; the remaining
stages are never executed.

This module is the deterministic executor that turns "here is the plan and here
is what we observed per stage" into "we promoted to 100%" or "we rolled back at
the 25% stage because the observed reward fell below the OPE DR CI lower bound".
It is pure: no clock, no I/O, no randomness — the same inputs always yield the
same decision, which is what makes a rollback auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.routing.promotion import PolicyCanaryPlan


@dataclass
class CanaryGuardrails:
    """Concrete thresholds the executor enforces at every stage.

    These are the numeric counterparts of the prose guardrails carried on a
    :class:`PolicyCanaryPlan`. ``dr_ci_lower_bound`` is the reward floor (the OPE
    DR CI lower bound from the promotion report): observed reward must not fall
    below it. High-risk failures and security regressions are zero-tolerance.
    """

    dr_ci_lower_bound: float
    max_human_review_rate: float
    max_cost: float
    allow_high_risk_failures: bool = False
    allow_security_regressions: bool = False


@dataclass
class CanaryStageResult:
    """Outcome of evaluating one staged-traffic step against the guardrails."""

    stage_fraction: float
    observed_reward: float
    observed_human_review_rate: float
    observed_cost: float
    high_risk_failures: int
    security_regressions: int
    passed: bool
    breach_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "stage_fraction": self.stage_fraction,
            "observed_reward": self.observed_reward,
            "observed_human_review_rate": self.observed_human_review_rate,
            "observed_cost": self.observed_cost,
            "high_risk_failures": self.high_risk_failures,
            "security_regressions": self.security_regressions,
            "passed": self.passed,
            "breach_reasons": self.breach_reasons,
        }


@dataclass
class CanaryRollbackDecision:
    """Terminal verdict of a canary run.

    ``rolled_back`` is ``False`` only when every stage passed (full promotion).
    When it is ``True``, ``stopped_at_stage`` is the breaching stage fraction and
    ``reason`` records why.
    """

    rolled_back: bool
    stopped_at_stage: float | None = None
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "rolled_back": self.rolled_back,
            "stopped_at_stage": self.stopped_at_stage,
            "reason": self.reason,
        }


class PolicyCanaryExecutor:
    """Deterministically simulate a staged canary rollout against guardrails.

    Construct with the :class:`PolicyCanaryPlan` produced by the promotion gate
    and the numeric :class:`CanaryGuardrails`, then call :meth:`run` with the
    per-stage observed metrics. Stages are walked in plan order; the first stage
    whose metrics breach any guardrail triggers rollback and the remaining stages
    are not executed. If every stage passes, the policy reaches full promotion
    and no rollback is issued.
    """

    def __init__(self, plan: PolicyCanaryPlan, guardrails: CanaryGuardrails) -> None:
        self.plan = plan
        self.guardrails = guardrails

    def _evaluate_stage(self, fraction: float, metrics: dict) -> CanaryStageResult:
        g = self.guardrails
        reward = float(metrics.get("observed_reward", 0.0))
        hr_rate = float(metrics.get("observed_human_review_rate", 0.0))
        cost = float(metrics.get("observed_cost", 0.0))
        high_risk = int(metrics.get("high_risk_failures", 0))
        security = int(metrics.get("security_regressions", 0))

        reasons: list[str] = []
        if reward < g.dr_ci_lower_bound - 1e-9:
            reasons.append(
                f"observed reward {reward:.3f} below DR CI lower bound "
                f"{g.dr_ci_lower_bound:.3f}"
            )
        if hr_rate > g.max_human_review_rate + 1e-9:
            reasons.append(
                f"human-review rate {hr_rate:.3f} exceeds cap "
                f"{g.max_human_review_rate:.3f}"
            )
        if cost > g.max_cost + 1e-9:
            reasons.append(f"cost {cost:.4f} exceeds cap {g.max_cost:.4f}")
        if high_risk > 0 and not g.allow_high_risk_failures:
            reasons.append(f"{high_risk} high-risk task failure(s)")
        if security > 0 and not g.allow_security_regressions:
            reasons.append(f"{security} security regression(s)")

        return CanaryStageResult(
            stage_fraction=fraction,
            observed_reward=reward,
            observed_human_review_rate=hr_rate,
            observed_cost=cost,
            high_risk_failures=high_risk,
            security_regressions=security,
            passed=not reasons,
            breach_reasons=reasons,
        )

    def run(
        self, stage_metrics: list[dict]
    ) -> tuple[list[CanaryStageResult], CanaryRollbackDecision]:
        """Walk the plan's stages against ``stage_metrics`` (one dict per stage).

        Returns the per-stage results that were actually executed and the
        terminal rollback decision. Evaluation stops at the first breaching
        stage, so ``results`` may be shorter than ``self.plan.stages``.
        """
        results: list[CanaryStageResult] = []
        for fraction, metrics in zip(self.plan.stages, stage_metrics, strict=False):
            result = self._evaluate_stage(fraction, metrics)
            results.append(result)
            if not result.passed:
                return results, CanaryRollbackDecision(
                    rolled_back=True,
                    stopped_at_stage=fraction,
                    reason="; ".join(result.breach_reasons),
                )
        return results, CanaryRollbackDecision(rolled_back=False)
