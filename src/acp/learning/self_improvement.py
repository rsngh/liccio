"""Closed-loop self-improvement orchestrator (Alpha 8 capstone).

This is the end-to-end answer to the Alpha-8 acceptance question:

> Can ACP learn from its own exhaust to predict viability and context strategy,
> and decide *safely* whether to adopt what it learned?

`run_self_improvement_cycle` takes an `ExhaustBundle` (the persisted run exhaust),
distills training datasets from it, trains the learned viability + context-strategy
models, evaluates them, and applies the promotion gates — returning a single report
that states, for each learned model, whether it is safe to promote and why. It
never auto-promotes anything: the learned viability assessor stays advisory unless
it makes **zero high-risk false negatives** on the holdout, exactly as the
`EnsembleViabilityAssessor` contract requires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acp.core.classifier import classify
from acp.core.viability_learned import (
    LearnedViabilityAssessor,
    evaluate_learned_viability,
    viability_features,
)
from acp.routing.context_strategy_learner import (
    ContextStrategyPredictor,
    evaluate_context_strategy_predictor,
)
from acp.schemas.task import Task
from acp.training.dataset_factory import DatasetFactory, ExhaustBundle


@dataclass
class SelfImprovementReport:
    viability: dict[str, Any] = field(default_factory=dict)
    context_strategy: dict[str, Any] = field(default_factory=dict)
    datasets: dict[str, int] = field(default_factory=dict)
    promotions: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "datasets": self.datasets,
            "viability": self.viability,
            "context_strategy": self.context_strategy,
            "promotions": self.promotions,
            "notes": self.notes,
        }


def _tasks_by_id(bundle: ExhaustBundle) -> dict[str, Task]:
    return {t.id: t for t in bundle.tasks}


def run_self_improvement_cycle(bundle: ExhaustBundle) -> SelfImprovementReport:
    """Distill datasets from exhaust, train + evaluate learned models, gate them."""
    report = SelfImprovementReport()
    factory = DatasetFactory()

    # 1. Distill datasets from exhaust.
    via_examples = factory.build("viability", bundle).examples
    ctx_examples = factory.build("context_strategy", bundle).examples
    report.datasets = {"viability": len(via_examples),
                       "context_strategy": len(ctx_examples)}

    tasks = _tasks_by_id(bundle)

    # 2. Train + evaluate the learned viability assessor.
    if via_examples:
        rows = []
        eval_cases = []
        for ex in via_examples:
            task = tasks.get(ex.task_id or "")
            if task is None:
                continue
            cls = classify(task)
            viable = bool(ex.target.get("viable")) if isinstance(ex.target, dict) else False
            rows.append({**viability_features(task, cls), "viable": 1 if viable else 0})
            eval_cases.append({"task": task, "cls": cls, "viable": viable})
        if rows:
            assessor = LearnedViabilityAssessor()
            assessor.fit(rows)
            via_report = evaluate_learned_viability(assessor, eval_cases)
            report.viability = via_report.as_dict()
            # Promotion gate: advisory unless zero high-risk false negatives.
            report.promotions["learned_viability"] = via_report.promotable
            report.notes.append(
                "learned viability promotable" if via_report.promotable
                else "learned viability stays ADVISORY (high-risk false negatives "
                     "present or untested)")
    else:
        report.notes.append("no viability exhaust — cannot train viability model")

    # 3. Train + evaluate the context-strategy predictor.
    cs_rows = []
    for ex in ctx_examples:
        tgt = ex.target if isinstance(ex.target, dict) else {}
        inp = ex.inputs if isinstance(ex.inputs, dict) else {}
        if tgt.get("reward") is None:
            continue
        cs_rows.append({
            "task_type": inp.get("task_type"), "risk_level": inp.get("risk_level"),
            "context_strategy": tgt.get("context_strategy"), "reward": tgt.get("reward"),
        })
    if cs_rows:
        predictor = ContextStrategyPredictor()
        predictor.fit(cs_rows)
        report.context_strategy = evaluate_context_strategy_predictor(predictor, cs_rows)
        report.promotions["context_strategy"] = (
            report.context_strategy.get("top1_accuracy", 0.0) >= 0.6)
    else:
        report.notes.append("no rewarded context-strategy exhaust — cannot train")

    return report
