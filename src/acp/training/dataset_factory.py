"""Distill ACP run exhaust into versioned training datasets (Alpha-7 WS3).

The :class:`DatasetFactory` consumes persisted entities (traces, evaluations,
weak/human labels, routing decisions, rewards, tasks) and emits validated
:class:`TrainingExample` records grouped into a hashed :class:`DatasetVersion`.

Mandatory, deterministic behavior (no RNG pitfalls):

* **Temporal split** — examples created on/after ``temporal_split_at`` go to
  ``test``; everything else trains.
* **Repo split** — tasks whose ``repo_id`` is in ``repo_holdout`` go to a
  ``holdout`` split (and never leak into train).
* **Deduplication** — collapse examples sharing a content hash (first wins).
* **Redaction** — every example payload passes through ``redact_report`` /
  :class:`~acp.core.redaction.Redactor` before it leaves the factory.
* **Generated-file filtering** — drop build/caches from any file lists.
* **Leakage audit** — scan redacted examples for surviving secret shapes and
  for train/test id or repo-holdout violations.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from acp.core.redaction import DEFAULT_VALUE_PATTERNS, Redactor
from acp.observability.live_report import redact_report
from acp.schemas.evaluation import EvaluationResult, WeakLabel
from acp.schemas.human_review import HumanLabel
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingDecision
from acp.schemas.task import Task
from acp.schemas.trace import AgentTrace
from acp.schemas.training import (
    DatasetBuildConfig,
    DatasetCard,
    DatasetVersion,
    LeakageAudit,
    RedactionReport,
    TrainingExample,
)

# Path fragments that mark generated / non-source files we never train on.
_GENERATED_MARKERS: tuple[str, ...] = (
    "__pycache__",
    ".coverage",
    "node_modules",
)
_GENERATED_SUFFIXES: tuple[str, ...] = (".pyc",)
_GENERATED_DIRS: tuple[str, ...] = ("dist/", "build/")

# Dataset kinds this factory understands.
SUPPORTED_KINDS: tuple[str, ...] = (
    "viability",
    "routing",
    "context_strategy",
    "human_review",
    "evaluator",
    "repair",
    "trace_summary",
    "verification_plan",
)


def _is_generated(path: str) -> bool:
    p = str(path)
    if any(marker in p for marker in _GENERATED_MARKERS):
        return True
    if p.endswith(_GENERATED_SUFFIXES):
        return True
    norm = p.replace("\\", "/")
    return any(seg in (norm + "/") for seg in _GENERATED_DIRS) or any(
        norm == d.rstrip("/") or norm.startswith(d) for d in _GENERATED_DIRS
    )


def filter_generated_files(paths: Iterable[str]) -> list[str]:
    """Drop generated / cache files from a list of paths."""
    return [p for p in paths if not _is_generated(str(p))]


class ExhaustBundle:
    """Container of persisted entities the factory distills from.

    Decoupled from the DB so the factory is pure and testable; the service
    layer can populate it from ``EntityStore.list_by`` / ``all_for_task``.
    """

    def __init__(
        self,
        *,
        tasks: Iterable[Task] = (),
        traces: Iterable[AgentTrace] = (),
        evaluations: Iterable[EvaluationResult] = (),
        weak_labels: Iterable[WeakLabel] = (),
        human_labels: Iterable[HumanLabel] = (),
        routing_decisions: Iterable[RoutingDecision] = (),
        rewards: Iterable[RewardEvent] = (),
    ) -> None:
        self.tasks: list[Task] = list(tasks)
        self.traces: list[AgentTrace] = list(traces)
        self.evaluations: list[EvaluationResult] = list(evaluations)
        self.weak_labels: list[WeakLabel] = list(weak_labels)
        self.human_labels: list[HumanLabel] = list(human_labels)
        self.routing_decisions: list[RoutingDecision] = list(routing_decisions)
        self.rewards: list[RewardEvent] = list(rewards)

    def task_repo(self, task_id: str | None) -> str | None:
        for t in self.tasks:
            if t.id == task_id:
                return t.repo_id
        return None


class BuildResult:
    """Output of a dataset build: examples + version + audits."""

    def __init__(
        self,
        examples: list[TrainingExample],
        version: DatasetVersion,
        redaction: RedactionReport,
        leakage: LeakageAudit,
        card: DatasetCard,
    ) -> None:
        self.examples = examples
        self.version = version
        self.redaction = redaction
        self.leakage = leakage
        self.card = card


class DatasetFactory:
    """Builds redacted, leakage-audited training datasets from run exhaust."""

    def __init__(self, redactor: Redactor | None = None) -> None:
        self._redactor = redactor or Redactor()

    # -- public API --------------------------------------------------------

    def build(
        self,
        kind: str,
        bundle: ExhaustBundle,
        config: DatasetBuildConfig | None = None,
        *,
        version: str = "1",
    ) -> BuildResult:
        """Build a dataset of ``kind`` from ``bundle`` deterministically."""
        if kind not in SUPPORTED_KINDS:
            raise ValueError(f"unknown dataset kind: {kind!r}")
        cfg = config or DatasetBuildConfig(kind=kind)

        raw = self._distill(kind, bundle, cfg)
        if cfg.drop_generated_files:
            raw = [self._scrub_files(ex) for ex in raw]
        redaction = RedactionReport(
            redactor_value_patterns=len(DEFAULT_VALUE_PATTERNS),
        )
        examples = [self._redact_example(ex, redaction) for ex in raw]
        if cfg.dedup:
            examples = self._dedup(examples)
        self._assign_splits(examples, bundle, cfg)

        leakage = self._audit(examples, bundle, cfg)
        card = self._build_card(kind, examples, bundle, redaction, leakage)
        ver = DatasetVersion(
            kind=kind,
            version=version,
            n_examples=len(examples),
            splits=card.splits,
            build_config=cfg.model_dump(mode="json"),
            card=card.model_dump(mode="json"),
        )
        return BuildResult(examples, ver, redaction, leakage, card)

    # -- distillers --------------------------------------------------------

    def _distill(
        self, kind: str, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        builder = {
            "routing": self._build_routing,
            "human_review": self._build_human_review,
            "evaluator": self._build_evaluator,
            "repair": self._build_repair,
            "viability": self._build_viability,
            "context_strategy": self._build_context_strategy,
            "trace_summary": self._build_trace_summary,
            "verification_plan": self._build_verification_plan,
        }[kind]
        return builder(bundle, cfg)

    def _build_routing(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """Predict the chosen routing action from the task, supervised by reward."""
        rewards_by_decision = {
            r.routing_decision_id: r for r in bundle.rewards if r.routing_decision_id
        }
        tasks = {t.id: t for t in bundle.tasks}
        out: list[TrainingExample] = []
        for dec in bundle.routing_decisions:
            task = tasks.get(dec.task_id)
            reward = rewards_by_decision.get(dec.id)
            out.append(
                TrainingExample(
                    dataset_kind="routing",
                    task_id=dec.task_id,
                    inputs={
                        "task_type": (task.task_type if task else None),
                        "risk_level": (task.risk_level if task else None),
                        "ambiguity_score": (task.ambiguity_score if task else None),
                        "policy_version": dec.policy_version,
                        "candidate_action_keys": [a.key() for a in dec.candidate_actions],
                    },
                    target={
                        "action_key": dec.action.key(),
                        "agent_name": dec.action.agent_name,
                        "model_name": dec.action.model_name,
                        "context_strategy": dec.action.context_strategy,
                    },
                    label_source=(reward.label_source if reward else "derived"),
                    created_at=dec.created_at,
                    provenance={
                        "routing_decision_id": dec.id,
                        "reward": (reward.reward if reward else None),
                        "action_probability": dec.action_probability,
                    },
                )
            )
        return out

    def _build_human_review(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """Predict the human verdict for a task attempt (gold labels)."""
        evals: dict[tuple[str, str | None], EvaluationResult] = {
            (e.task_id, e.attempt_id): e for e in bundle.evaluations
        }
        out: list[TrainingExample] = []
        for hl in bundle.human_labels:
            if hl.score < cfg.min_label_confidence:
                continue
            ev = evals.get((hl.task_id, hl.attempt_id))
            out.append(
                TrainingExample(
                    dataset_kind="human_review",
                    task_id=hl.task_id,
                    inputs={
                        "spec_compliance": (ev.spec_compliance if ev else None),
                        "security_risk": (ev.security_risk if ev else None),
                        "regression_risk": (ev.regression_risk if ev else None),
                        "evaluator_reasons": (list(ev.reasons) if ev else []),
                    },
                    target={"verdict": hl.verdict, "score": hl.score},
                    label_source="human",
                    created_at=hl.created_at,
                    provenance={
                        "human_label_id": hl.id,
                        "reviewer": hl.reviewer,
                        "review_item_id": hl.review_item_id,
                    },
                )
            )
        return out

    def _build_evaluator(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """Reproduce evaluator scores from trace features (distillation)."""
        traces: dict[tuple[str | None, str | None], AgentTrace] = {
            (t.task_id, t.attempt_id): t for t in bundle.traces
        }
        out: list[TrainingExample] = []
        for ev in bundle.evaluations:
            tr = traces.get((ev.task_id, ev.attempt_id))
            out.append(
                TrainingExample(
                    dataset_kind="evaluator",
                    task_id=ev.task_id,
                    inputs={
                        "changed_files": (list(tr.changed_files) if tr else []),
                        "diff_lines": (tr.diff_lines if tr else 0),
                        "tool_calls": (tr.tool_calls if tr else 0),
                        "status": (tr.status if tr else None),
                    },
                    target={
                        "spec_compliance": ev.spec_compliance,
                        "security_risk": ev.security_risk,
                        "requires_human_review": ev.requires_human_review,
                    },
                    label_source="objective",
                    created_at=ev.created_at,
                    provenance={"evaluation_id": ev.id, "attempt_id": ev.attempt_id},
                )
            )
        return out

    def _build_repair(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """Distill successful repairs: task -> changed files (success only)."""
        tasks = {t.id: t for t in bundle.tasks}
        out: list[TrainingExample] = []
        for tr in bundle.traces:
            if tr.status != "succeeded" or not tr.changed_files:
                continue
            task = tasks.get(tr.task_id) if tr.task_id else None
            out.append(
                TrainingExample(
                    dataset_kind="repair",
                    task_id=tr.task_id,
                    inputs={
                        "title": (task.title if task else None),
                        "body": (task.body if task else None),
                        "task_type": (task.task_type if task else None),
                    },
                    target={
                        "changed_files": list(tr.changed_files),
                        "diff_lines": tr.diff_lines,
                    },
                    label_source="objective",
                    created_at=tr.created_at,
                    provenance={"trace_id": tr.id, "adapter_name": tr.adapter_name},
                )
            )
        return out

    def _build_viability(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """Task features -> was the task solvable by an agent? (Alpha 8 WS6).

        Label = "viable" when any trace for the task succeeded (objective), else
        "not_viable". This is the supervised target for the learned viability
        assessor (WS2).
        """
        tasks = {t.id: t for t in bundle.tasks}
        # Per task: did any attempt succeed?
        solved: dict[str, bool] = {}
        for tr in bundle.traces:
            if not tr.task_id:
                continue
            solved[tr.task_id] = solved.get(tr.task_id, False) or (tr.status == "succeeded")
        out: list[TrainingExample] = []
        for task_id, ok in solved.items():
            task = tasks.get(task_id)
            if task is None:
                continue
            out.append(TrainingExample(
                dataset_kind="viability", task_id=task_id,
                inputs={
                    "task_type": task.task_type,
                    "risk_level": task.risk_level,
                    "ambiguity_score": getattr(task, "ambiguity_score", None),
                    "has_acceptance_criteria": bool(task.acceptance_criteria),
                    "body_len": len(task.body or ""),
                },
                target={"viable": ok},
                label_source="objective",
                created_at=getattr(task, "created_at", None),
                provenance={"derived_from": "trace_outcomes"},
            ))
        return out

    def _build_context_strategy(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """(task features, routed context strategy) -> reward (Alpha 8 WS6).

        Lets the context-strategy learner (WS3) learn which strategy maximizes
        downstream reward per task class, supervised by the logged reward.
        """
        rewards_by_decision = {
            r.routing_decision_id: r for r in bundle.rewards if r.routing_decision_id
        }
        tasks = {t.id: t for t in bundle.tasks}
        out: list[TrainingExample] = []
        for dec in bundle.routing_decisions:
            reward = rewards_by_decision.get(dec.id)
            task = tasks.get(dec.task_id)
            out.append(TrainingExample(
                dataset_kind="context_strategy", task_id=dec.task_id,
                inputs={
                    "task_type": (task.task_type if task else None),
                    "risk_level": (task.risk_level if task else None),
                    "context_strategy": dec.action.context_strategy,
                },
                target={"context_strategy": dec.action.context_strategy,
                        "reward": (reward.reward if reward else None)},
                label_source=(reward.label_source if reward else "derived"),
                created_at=dec.created_at,
                provenance={"routing_decision_id": dec.id},
            ))
        return out

    def _build_trace_summary(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """Trace -> a deterministic structured summary string (Alpha 8 WS6).

        A no-LLM, templated summary so the dataset is reproducible; a fine-tuned
        summarizer can later replace the template.
        """
        out: list[TrainingExample] = []
        for tr in bundle.traces:
            summary = (
                f"{tr.adapter_name} {tr.status}: {tr.tool_calls} tool calls, "
                f"{len(tr.changed_files)} files changed ({tr.diff_lines} diff lines), "
                f"{tr.input_tokens + tr.output_tokens} tokens, "
                f"${tr.estimated_cost_usd:.4f}."
            )
            out.append(TrainingExample(
                dataset_kind="trace_summary", task_id=tr.task_id,
                inputs={
                    "adapter_name": tr.adapter_name, "status": tr.status,
                    "tool_calls": tr.tool_calls, "changed_files": list(tr.changed_files),
                    "diff_lines": tr.diff_lines,
                },
                target=summary, label_source="derived",
                created_at=tr.created_at,
                provenance={"trace_id": tr.id},
            ))
        return out

    def _build_verification_plan(
        self, bundle: ExhaustBundle, cfg: DatasetBuildConfig
    ) -> list[TrainingExample]:
        """Task -> required verification kinds (Alpha 8 WS6).

        Distilled from the deterministic classifier so a model can learn to
        predict the verification plan directly from the task.
        """
        from acp.core.classifier import classify

        out: list[TrainingExample] = []
        for task in bundle.tasks:
            cls = classify(task)
            out.append(TrainingExample(
                dataset_kind="verification_plan", task_id=task.id,
                inputs={"title": task.title, "task_type": cls.task_type.value
                        if hasattr(cls.task_type, "value") else cls.task_type},
                target={"required_verification_kinds": list(cls.required_verification_kinds)},
                label_source="derived",
                created_at=getattr(task, "created_at", None),
                provenance={"classifier": "deterministic"},
            ))
        return out

    # -- pipeline stages ---------------------------------------------------

    def _scrub_files(self, ex: TrainingExample) -> TrainingExample:
        """Drop generated files from any path-like list in inputs/target."""

        def scrub(obj: Any) -> Any:
            if isinstance(obj, Mapping):
                return {k: scrub(v) for k, v in obj.items()}
            if isinstance(obj, list) and obj and all(isinstance(v, str) for v in obj):
                if any(("/" in v or v.endswith(".py") or "." in v) for v in obj):
                    return filter_generated_files(obj)
                return obj
            return obj

        ex.inputs = scrub(ex.inputs)
        ex.target = scrub(ex.target)
        return ex

    def _redact_example(
        self, ex: TrainingExample, report: RedactionReport
    ) -> TrainingExample:
        report.examples_scanned += 1
        before = (ex.inputs, ex.target, ex.provenance)
        ex.inputs = redact_report(ex.inputs)
        ex.target = redact_report(ex.target)
        ex.provenance = redact_report(ex.provenance)
        secrets = self._count_secrets(before)
        if secrets:
            report.examples_modified += 1
            report.secrets_redacted += secrets
        return ex

    def _count_secrets(self, payload: Any) -> int:
        text = str(payload)
        return sum(len(rx.findall(text)) for rx in self._value_res())

    def _value_res(self) -> list[re.Pattern[str]]:
        return [re.compile(p) for p in DEFAULT_VALUE_PATTERNS]

    def _dedup(self, examples: list[TrainingExample]) -> list[TrainingExample]:
        seen: set[str] = set()
        out: list[TrainingExample] = []
        for ex in examples:
            h = ex.content_hash()
            if h in seen:
                continue
            seen.add(h)
            out.append(ex)
        return out

    def _assign_splits(
        self,
        examples: list[TrainingExample],
        bundle: ExhaustBundle,
        cfg: DatasetBuildConfig,
    ) -> None:
        for ex in examples:
            repo = bundle.task_repo(ex.task_id)
            if repo is not None and repo in cfg.repo_holdout:
                ex.split = "holdout"
            elif (
                cfg.temporal_split_at is not None
                and ex.created_at >= cfg.temporal_split_at
            ):
                ex.split = "test"
            else:
                ex.split = "train"

    def _audit(
        self,
        examples: list[TrainingExample],
        bundle: ExhaustBundle,
        cfg: DatasetBuildConfig,
    ) -> LeakageAudit:
        findings: list[str] = []
        value_res = self._value_res()
        survivors = 0
        for ex in examples:
            blob = ex.canonical_json()
            for rx in value_res:
                survivors += len(rx.findall(blob))
        if survivors:
            findings.append(f"{survivors} secret-shaped tokens survived redaction")

        by_split: dict[str, set[str]] = {}
        for ex in examples:
            by_split.setdefault(ex.split, set()).add(ex.id)
        overlap = len(by_split.get("train", set()) & by_split.get("test", set()))
        if overlap:
            findings.append(f"{overlap} ids in both train and test")

        repo_violations = 0
        for ex in examples:
            repo = bundle.task_repo(ex.task_id)
            if repo in cfg.repo_holdout and ex.split != "holdout":
                repo_violations += 1
        if repo_violations:
            findings.append(f"{repo_violations} holdout-repo examples leaked into train/test")

        return LeakageAudit(
            examples_scanned=len(examples),
            secret_survivors=survivors,
            train_test_id_overlap=overlap,
            repo_holdout_violations=repo_violations,
            clean=not findings,
            findings=findings,
        )

    def _build_card(
        self,
        kind: str,
        examples: list[TrainingExample],
        bundle: ExhaustBundle,
        redaction: RedactionReport,
        leakage: LeakageAudit,
    ) -> DatasetCard:
        label_sources: dict[str, int] = {}
        splits: dict[str, int] = {}
        tasks: set[str] = set()
        for ex in examples:
            label_sources[ex.label_source] = label_sources.get(ex.label_source, 0) + 1
            splits[ex.split] = splits.get(ex.split, 0) + 1
            if ex.task_id:
                tasks.add(ex.task_id)
        notes: list[str] = []
        if not examples:
            notes.append(f"{kind} distillation produced no examples "
                         "(insufficient exhaust of this kind)")
        return DatasetCard(
            kind=kind,
            description=f"ACP run-exhaust dataset for {kind}",
            n_examples=len(examples),
            label_sources=label_sources,
            splits=splits,
            source_tasks=len(tasks),
            redaction=redaction,
            leakage=leakage,
            notes=notes,
        )
