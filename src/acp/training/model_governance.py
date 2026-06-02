"""Fine-tuning governance (Alpha 8, WS8).

A learned/fine-tuned model may only be promoted when it provably beats the
baselines it would replace and is safe: it must beat the rules baseline and the
prompt baseline, pass temporal and repo holdouts, pass leakage + memorization
audits, not degrade high-risk cases, fit cost/latency budgets, and ship with a
rollback plan. The `ModelPromotionGate` encodes that contract; `MemorizationAudit`
verifies a model does not regurgitate holdout secret canaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FineTuneCandidate:
    model_run_id: str
    base_model: str
    dataset_kind: str
    n_train: int
    n_test: int


@dataclass
class MemorizationAudit:
    """Checks model outputs do not reproduce holdout secret canaries."""

    canaries: list[str] = field(default_factory=list)

    def audit(self, outputs: list[str]) -> dict:
        blob = "\n".join(outputs)
        leaked = [c for c in self.canaries if c and c in blob]
        return {"canaries": len(self.canaries), "leaked": leaked, "clean": not leaked}


@dataclass
class ConditionResult:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class ModelPromotionDecision:
    promote: bool
    conditions: list[ConditionResult]
    reasons: list[str]

    def as_dict(self) -> dict:
        return {"promote": self.promote, "reasons": self.reasons,
                "conditions": [c.as_dict() for c in self.conditions]}


@dataclass
class ModelPromotionGate:
    """Gate a fine-tuned model from candidate to promoted."""

    min_lift_vs_rules: float = 0.0       # candidate_acc - rules_acc must exceed this
    min_lift_vs_prompt: float = 0.0
    max_high_risk_degradation: float = 0.0
    max_cost_ratio: float = 1.5
    max_latency_ratio: float = 2.0

    def evaluate(
        self,
        *,
        candidate_accuracy: float,
        rules_baseline_accuracy: float,
        prompt_baseline_accuracy: float,
        temporal_holdout_passed: bool,
        repo_holdout_passed: bool,
        leakage_clean: bool,
        memorization_clean: bool,
        high_risk_degradation: float,
        cost_ratio: float = 1.0,
        latency_ratio: float = 1.0,
        rollback_plan: str | None = None,
    ) -> ModelPromotionDecision:
        conds = [
            ConditionResult("beats_rules_baseline",
                            candidate_accuracy - rules_baseline_accuracy > self.min_lift_vs_rules,
                            f"candidate {candidate_accuracy:.3f} vs rules "
                            f"{rules_baseline_accuracy:.3f}"),
            ConditionResult("beats_prompt_baseline",
                            candidate_accuracy - prompt_baseline_accuracy > self.min_lift_vs_prompt,
                            f"candidate {candidate_accuracy:.3f} vs prompt "
                            f"{prompt_baseline_accuracy:.3f}"),
            ConditionResult("temporal_holdout", temporal_holdout_passed,
                            "temporal holdout generalization"),
            ConditionResult("repo_holdout", repo_holdout_passed,
                            "cross-repo generalization"),
            ConditionResult("leakage_audit", leakage_clean, "no secret leakage in data"),
            ConditionResult("memorization_audit", memorization_clean,
                            "no holdout canary memorization"),
            ConditionResult("high_risk_not_degraded",
                            high_risk_degradation <= self.max_high_risk_degradation + 1e-9,
                            f"high-risk degradation {high_risk_degradation:+.3f}"),
            ConditionResult("cost_acceptable", cost_ratio <= self.max_cost_ratio + 1e-9,
                            f"cost ratio {cost_ratio:.2f} vs cap {self.max_cost_ratio}"),
            ConditionResult("latency_acceptable",
                            latency_ratio <= self.max_latency_ratio + 1e-9,
                            f"latency ratio {latency_ratio:.2f} vs cap {self.max_latency_ratio}"),
            ConditionResult("rollback_plan_exists", bool(rollback_plan),
                            rollback_plan or "no rollback plan provided"),
        ]
        failed = [c for c in conds if not c.passed]
        promote = not failed
        reasons = ([f"blocked: {c.name} ({c.detail})" for c in failed] if failed
                   else ["all model-promotion conditions satisfied"])
        return ModelPromotionDecision(promote=promote, conditions=conds, reasons=reasons)
