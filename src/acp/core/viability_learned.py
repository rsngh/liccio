"""Learned + ensemble viability assessment (Alpha 8, WS2).

Alpha 7's `assess_viability` is a deterministic rules assessor. WS2 adds a
*learned* assessor trained on viability examples distilled from ACP exhaust, and
an *ensemble* that combines them under a strict safety contract:

  the learned assessor may **advise** (sharpen confidence, suggest a cheaper
  path) but may **not override** the rules' safety decisions — abstain,
  ``true_harness_required``, ``human_review_required`` — until it has been proven
  to make **zero high-risk false negatives** on a holdout set.

A high-risk false negative (predicting "viable / safe to auto-attempt" when the
truth is failure) is the costliest mistake, so it gates promotion of the learned
model from advisory to authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.core.enums import RiskLevel, TaskType
from acp.core.viability import assess_viability
from acp.routing.supervised import TrainResult, predict, train_predictor
from acp.schemas.task import Task, TaskClassification
from acp.schemas.viability import ViabilityAssessment

_FEATURE_KEYS = [
    "risk_rank", "ambiguity_score", "testability_score", "has_acceptance_criteria",
    "body_len", "is_security", "is_docs", "is_migration",
]


def viability_features(task: Task, cls: TaskClassification) -> dict[str, float]:
    ttype = cls.task_type if isinstance(cls.task_type, TaskType) else TaskType(cls.task_type)
    risk = cls.risk_level if isinstance(cls.risk_level, RiskLevel) else RiskLevel(cls.risk_level)
    return {
        "risk_rank": float(risk.rank),
        "ambiguity_score": float(cls.ambiguity_score),
        "testability_score": float(cls.testability_score),
        "has_acceptance_criteria": 1.0 if task.acceptance_criteria else 0.0,
        "body_len": float(len(task.body or "")),
        "is_security": 1.0 if ttype == TaskType.SECURITY_FIX else 0.0,
        "is_docs": 1.0 if ttype == TaskType.DOCS else 0.0,
        "is_migration": 1.0 if ttype == TaskType.MIGRATION else 0.0,
    }


class RuleViabilityAssessor:
    """Thin wrapper over the deterministic Alpha-7 assessor."""

    name = "rules"

    def assess(self, task: Task, cls: TaskClassification) -> ViabilityAssessment:
        return assess_viability(task, cls)


@dataclass
class LearnedViabilityAssessor:
    """Predicts P(viable) from task features, trained on distilled exhaust."""

    name: str = "learned"
    _model: TrainResult | None = None

    def fit(self, rows: list[dict[str, Any]]) -> None:
        """Rows of ``{**features, "viable": 0/1}``."""
        self._model = train_predictor(rows, "viable", _FEATURE_KEYS)

    def predict_viable(self, task: Task, cls: TaskClassification) -> float:
        if self._model is None:
            return 0.5
        p = predict(self._model, viability_features(task, cls))
        return max(0.0, min(1.0, p))


@dataclass
class EnsembleViabilityAssessor:
    """Rules + learned. Learned advises; rules retain safety authority until the
    learned model is *promoted* (zero high-risk false negatives on holdout)."""

    learned: LearnedViabilityAssessor = field(default_factory=LearnedViabilityAssessor)
    rules: RuleViabilityAssessor = field(default_factory=RuleViabilityAssessor)
    learned_promoted: bool = False
    viable_threshold: float = 0.5

    def assess(self, task: Task, cls: TaskClassification) -> ViabilityAssessment:
        base = self.rules.assess(task, cls)
        p = self.learned.predict_viable(task, cls)
        base.supporting_features["learned_viable_prob"] = round(p, 4)
        # Advisory by default: never relaxes a safety decision.
        if not self.learned_promoted:
            base.supporting_features["learned_mode"] = 1.0  # advisory
            return base
        # Promoted: the learned model may relax *non-safety* optimism — e.g. lower
        # confidence when it strongly disagrees — but still never flips abstain or
        # harness/human-review requirements on high-risk tasks.
        risk = cls.risk_level if isinstance(cls.risk_level, RiskLevel) \
            else RiskLevel(cls.risk_level)
        if p < self.viable_threshold and risk.rank < RiskLevel.HIGH.rank and not base.abstain:
            base.confidence = round(min(base.confidence, 0.5 + 0.5 * p), 3)
        return base


@dataclass
class ViabilityEvaluationReport:
    n: int
    accuracy: float
    precision: float
    recall: float
    brier: float
    ece: float
    abstention_precision: float
    human_review_recall: float
    high_risk_false_negative_rate: float
    promotable: bool

    def as_dict(self) -> dict:
        return {
            "n": self.n, "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4), "recall": round(self.recall, 4),
            "brier": round(self.brier, 4), "ece": round(self.ece, 4),
            "abstention_precision": round(self.abstention_precision, 4),
            "human_review_recall": round(self.human_review_recall, 4),
            "high_risk_false_negative_rate": round(self.high_risk_false_negative_rate, 4),
            "promotable": self.promotable,
        }


def evaluate_learned_viability(
    assessor: LearnedViabilityAssessor,
    cases: list[dict[str, Any]],
    *,
    threshold: float = 0.5,
) -> ViabilityEvaluationReport:
    """Evaluate a learned assessor on labeled cases.

    Each case: ``{"task": Task, "cls": TaskClassification, "viable": bool}``. The
    promotion condition is **zero high-risk false negatives**.
    """
    from acp.evaluation.calibration_v2 import _ece

    preds: list[float] = []
    truths: list[bool] = []
    tp = fp = fn = tn = 0
    hr_fn = hr_total = 0  # high-risk false negatives
    abstain_correct = abstain_total = 0
    review_truth = review_caught = 0
    rules = RuleViabilityAssessor()
    for c in cases:
        task, cls, viable = c["task"], c["cls"], bool(c["viable"])
        p = assessor.predict_viable(task, cls)
        preds.append(p)
        truths.append(viable)
        pred_viable = p >= threshold
        if pred_viable and viable:
            tp += 1
        elif pred_viable and not viable:
            fp += 1
        elif not pred_viable and viable:
            fn += 1
        else:
            tn += 1
        risk = cls.risk_level if isinstance(cls.risk_level, RiskLevel) \
            else RiskLevel(cls.risk_level)
        # High-risk false negative: model says viable but task was NOT solvable.
        if risk.rank >= RiskLevel.HIGH.rank:
            hr_total += 1
            if pred_viable and not viable:
                hr_fn += 1
        # Rule-side abstention / human-review recall (advisory comparison).
        ra = rules.assess(task, cls)
        if ra.abstain:
            abstain_total += 1
            if not viable:
                abstain_correct += 1
        if not viable:
            review_truth += 1
            if ra.human_review_required or ra.abstain:
                review_caught += 1

    n = len(cases)
    acc = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    brier = sum((p - (1.0 if y else 0.0)) ** 2 for p, y in zip(preds, truths, strict=True)) / n \
        if n else 0.0
    ece = _ece(preds, [1.0 if y else 0.0 for y in truths])
    hr_fn_rate = hr_fn / hr_total if hr_total else 0.0
    return ViabilityEvaluationReport(
        n=n, accuracy=acc, precision=precision, recall=recall, brier=brier, ece=ece,
        abstention_precision=(abstain_correct / abstain_total if abstain_total else 1.0),
        human_review_recall=(review_caught / review_truth if review_truth else 1.0),
        high_risk_false_negative_rate=hr_fn_rate,
        promotable=(hr_fn == 0),
    )
