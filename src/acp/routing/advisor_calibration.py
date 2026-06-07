"""AdvisorPolicy v2 — calibrated triggers (GOALS Alpha 43 P2).

Turn advisor escalation from a heuristic into a calibrated decision: learn, per (task_type,
context_need) bucket, the cheap policy's base success and the advisor's uplift, then consult the
advisor only when its expected marginal value is positive (MetaCogAgent confidence-driven
delegation + CADMAS context-conditioned capability). Read-only by contract.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from acp.finops.advisor_marginal_value import advisor_marginal_value, is_advisor_waste

# advisor trigger features that, when present, raise the prior that escalation will help
TRIGGER_FEATURES = (
    "first_attempt_failed", "no_tests_run", "tests_failed", "hidden_verifier_uncertain",
    "diff_too_broad", "context_sufficiency_low", "retrieval_entropy_high",
    "cheap_policy_low_success_bucket", "high_risk_task", "underspecified_ticket",
    "memory_negative_prior_hit",
)


def _get(c: Any, k: str, d=None):
    return c.get(k, d) if isinstance(c, dict) else getattr(c, k, d)


@dataclass
class BucketStat:
    n: int = 0
    solved_cheap: int = 0
    n_advised: int = 0
    solved_advised: int = 0

    @property
    def base_rate(self) -> float:
        return self.solved_cheap / self.n if self.n else 0.0

    @property
    def advised_rate(self) -> float:
        return self.solved_advised / self.n_advised if self.n_advised else self.base_rate


class AdvisorCalibrator:
    """Learns advisor uplift per bucket and decides escalation by marginal value."""

    def __init__(self, advisor_cost: float = 0.002) -> None:
        self.advisor_cost = advisor_cost
        self._buckets: dict[str, BucketStat] = defaultdict(BucketStat)

    def fit(self, cells: list[Any]) -> AdvisorCalibrator:
        """cells: {bucket, solved_cheap, advisor_used, solved_after}."""
        for c in cells:
            b = self._buckets[str(_get(c, "bucket", "default"))]
            b.n += 1
            b.solved_cheap += int(bool(_get(c, "solved_cheap", False)))
            if _get(c, "advisor_used", False):
                b.n_advised += 1
                b.solved_advised += int(bool(_get(c, "solved_after", False)))
        return self

    def should_consult(self, *, bucket: str, budget_class: str = "normal_bugfix",
                       triggers: tuple[str, ...] = (), spend_so_far: float = 0.0) -> dict:
        st = self._buckets.get(bucket, BucketStat())
        base = st.base_rate
        # trigger features nudge the with-advisor estimate up; learned uplift dominates when present
        learned_uplift = max(0.0, st.advised_rate - st.base_rate)
        trigger_uplift = 0.05 * len([t for t in triggers if t in TRIGGER_FEATURES])
        p_with = min(1.0, base + max(learned_uplift, trigger_uplift))
        decision = advisor_marginal_value(
            p_solve_without_advisor=base, p_solve_with_advisor=p_with,
            advisor_cost=self.advisor_cost, budget_class=budget_class, spend_so_far=spend_so_far)
        return {"bucket": bucket, "should_consult": decision.should_call,
                "base_rate": round(base, 4), "p_with_advisor": round(p_with, 4),
                "expected_marginal_value": decision.expected_marginal_value,
                "reason": decision.reason, "triggers": list(triggers)}

    def trigger_quality(self, cells: list[Any]) -> dict:
        """Precision of advisor triggers: how many advisor calls changed the outcome."""
        advised = [c for c in cells if _get(c, "advisor_used", False)]
        if not advised:
            return {"n_advised": 0, "advisor_precision": None, "waste_rate": None}
        helped = sum(1 for c in advised if not is_advisor_waste(
            solved_without_advisor=bool(_get(c, "solved_cheap", False)),
            solved_with_advisor=bool(_get(c, "solved_after", False))))
        return {"n_advised": len(advised),
                "advisor_precision": round(helped / len(advised), 4),
                "waste_rate": round(1 - helped / len(advised), 4)}
