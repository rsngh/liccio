"""OPE-based policy promotion gate (Alpha 7, WS5).

Offline policy evaluation produces a *point estimate plus a confidence interval*
of a candidate policy's value. That alone is not a license to deploy: a high
estimate built on a log with no propensity overlap, a tiny effective sample size,
or a runaway importance weight is not trustworthy. The **promotion gate** turns
an OPE report into an auditable deploy/block decision by checking a battery of
conditions — statistical trust *and* operational safety — and refuses promotion
unless all required conditions pass.

This is the bridge from "we can estimate policies offline" (Alpha 6) to "we only
ship a policy that is provably safe to ship" (Alpha 7). A passing gate yields a
staged :class:`PolicyCanaryPlan`; a failing gate yields the exact reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.routing.ope import OPEReport


@dataclass
class PromotionThresholds:
    min_ess: float = 20.0            # effective sample size floor
    min_overlap: float = 0.8         # fraction of log the target would ever take
    max_weight: float = 50.0         # importance-weight ceiling (variance guard)
    min_dr_margin: float = 0.0       # DR CI lower bound must beat baseline by this
    require_snips_agreement: bool = True  # SNIPS must also beat baseline
    max_cost_ratio: float = 1.0      # target cost <= baseline * this
    max_human_review_ratio: float = 1.05  # target HR rate <= baseline * this
    require_high_risk_not_worse: bool = True
    min_calibration: float = 0.0     # evaluator calibration floor


@dataclass
class ConditionResult:
    name: str
    passed: bool
    detail: str
    value: float | None = None
    threshold: float | None = None
    required: bool = True

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail,
                "value": self.value, "threshold": self.threshold,
                "required": self.required}


@dataclass
class PolicyCanaryPlan:
    stages: list[float] = field(default_factory=lambda: [0.05, 0.25, 0.5, 1.0])
    guardrails: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"stages": self.stages, "guardrails": self.guardrails}


@dataclass
class PromotionDecision:
    promote: bool
    conditions: list[ConditionResult]
    reasons: list[str]
    canary_plan: PolicyCanaryPlan | None = None

    def as_dict(self) -> dict:
        return {
            "promote": self.promote,
            "reasons": self.reasons,
            "conditions": [c.as_dict() for c in self.conditions],
            "canary_plan": self.canary_plan.as_dict() if self.canary_plan else None,
        }


def evaluate_promotion(
    report: OPEReport,
    baseline_value: float,
    *,
    thresholds: PromotionThresholds | None = None,
    target_cost: float | None = None,
    baseline_cost: float | None = None,
    target_human_review_rate: float | None = None,
    baseline_human_review_rate: float | None = None,
    high_risk_value_delta: float | None = None,
    calibration_confidence: float | None = None,
) -> PromotionDecision:
    """Decide whether a candidate policy may be promoted from its OPE report.

    Optional operational metrics (cost, human-review rate, high-risk delta,
    calibration) are checked only when provided, so the gate degrades to the
    statistical-trust conditions on a thin log but tightens as more signal is
    available.
    """
    t = thresholds or PromotionThresholds()
    diag = report.diagnostics
    conds: list[ConditionResult] = []

    conds.append(ConditionResult(
        "effective_sample_size", diag.effective_sample_size >= t.min_ess,
        f"ESS {diag.effective_sample_size:.1f} vs floor {t.min_ess}",
        diag.effective_sample_size, t.min_ess))

    conds.append(ConditionResult(
        "propensity_overlap", diag.overlap >= t.min_overlap,
        f"overlap {diag.overlap:.2f} vs floor {t.min_overlap}",
        diag.overlap, t.min_overlap))

    conds.append(ConditionResult(
        "max_weight", diag.max_weight <= t.max_weight,
        f"max importance weight {diag.max_weight:.1f} vs ceiling {t.max_weight}",
        diag.max_weight, t.max_weight))

    dr_lb = report.dr.ci_low
    conds.append(ConditionResult(
        "dr_ci_beats_baseline", dr_lb >= baseline_value + t.min_dr_margin,
        f"DR CI lower bound {dr_lb:.3f} vs baseline {baseline_value:.3f}"
        f"+{t.min_dr_margin}", dr_lb, baseline_value + t.min_dr_margin))

    conds.append(ConditionResult(
        "snips_agrees", (not t.require_snips_agreement)
        or report.snips.value >= baseline_value,
        f"SNIPS {report.snips.value:.3f} vs baseline {baseline_value:.3f}",
        report.snips.value, baseline_value, required=t.require_snips_agreement))

    if target_cost is not None and baseline_cost is not None:
        cap = baseline_cost * t.max_cost_ratio
        conds.append(ConditionResult(
            "cost_cap", target_cost <= cap + 1e-9,
            f"target cost {target_cost:.4f} vs cap {cap:.4f}", target_cost, cap))

    if target_human_review_rate is not None and baseline_human_review_rate is not None:
        cap = baseline_human_review_rate * t.max_human_review_ratio
        conds.append(ConditionResult(
            "human_review_not_worse", target_human_review_rate <= cap + 1e-9,
            f"target HR rate {target_human_review_rate:.3f} vs cap {cap:.3f}",
            target_human_review_rate, cap))

    if high_risk_value_delta is not None:
        ok = (not t.require_high_risk_not_worse) or high_risk_value_delta >= -1e-9
        conds.append(ConditionResult(
            "high_risk_not_degraded", ok,
            f"high-risk value delta {high_risk_value_delta:+.3f}",
            high_risk_value_delta, 0.0, required=t.require_high_risk_not_worse))

    if calibration_confidence is not None:
        conds.append(ConditionResult(
            "calibration", calibration_confidence >= t.min_calibration,
            f"calibration {calibration_confidence:.2f} vs floor {t.min_calibration}",
            calibration_confidence, t.min_calibration))

    failed_required = [c for c in conds if c.required and not c.passed]
    promote = not failed_required
    reasons = ([f"blocked: {c.name} ({c.detail})" for c in failed_required]
               if not promote else ["all required conditions satisfied"])
    plan = _canary_plan(conds) if promote else None
    return PromotionDecision(promote=promote, conditions=conds, reasons=reasons,
                             canary_plan=plan)


def _canary_plan(conds: list[ConditionResult]) -> PolicyCanaryPlan:
    guardrails = [
        "roll back if observed reward < OPE DR CI lower bound over the stage window",
        "roll back if human-review rate exceeds the promotion cap",
        "hold at 5% until high-risk task outcomes are observed",
    ]
    # A thinner statistical margin warrants a slower ramp.
    ess = next((c.value for c in conds if c.name == "effective_sample_size"), None)
    stages = [0.05, 0.25, 0.5, 1.0] if (ess or 0) >= 50 else [0.02, 0.1, 0.25, 0.5, 1.0]
    return PolicyCanaryPlan(stages=stages, guardrails=guardrails)
