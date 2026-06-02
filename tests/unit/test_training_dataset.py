"""Tests for the Alpha-7 training-data factory (WS3/4/18)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from acp.core.enums import (
    AgentKind,
    HumanVerdict,
    RiskLevel,
    TaskType,
)
from acp.schemas.evaluation import EvaluationResult
from acp.schemas.human_review import HumanLabel
from acp.schemas.learning import RewardEvent
from acp.schemas.routing import RoutingAction, RoutingDecision
from acp.schemas.task import Task
from acp.schemas.trace import AgentTrace
from acp.schemas.training import DatasetBuildConfig, TrainingExample
from acp.training.candidate_report import build_candidate_report
from acp.training.dataset_factory import (
    DatasetFactory,
    ExhaustBundle,
    filter_generated_files,
)
from acp.training.exporters import export_hf_sft_jsonl, export_openai_jsonl
from acp.training.lora_smoke import TrainingDepsUnavailable, available, run_smoke

LEAK = "sk-LEAKTEST12345678901234567890"


def _dt(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def _bundle() -> ExhaustBundle:
    task_a = Task(id="task_a", repo_id="repo_x", title="fix a", task_type=TaskType.BUGFIX,
                  risk_level=RiskLevel.LOW, created_at=_dt(1))
    task_b = Task(id="task_b", repo_id="repo_holdout", title="fix b", created_at=_dt(20))
    action = RoutingAction(agent_kind=AgentKind.CLAUDE, agent_name="claude")
    dec = RoutingDecision(id="route_1", task_id="task_a", policy_version="v1",
                          action=action, action_probability=0.9, created_at=_dt(2))
    reward = RewardEvent(routing_decision_id="route_1", task_id="task_a", reward=1.0,
                         components={"objective": 1.0}, label_source="objective")
    ev = EvaluationResult(id="eval_1", task_id="task_a", attempt_id="att_1",
                          spec_compliance=0.9, security_risk=0.1, created_at=_dt(3))
    tr = AgentTrace(id="atrace_1", attempt_id="att_1", task_id="task_a",
                    adapter_name="claude", status="succeeded",
                    changed_files=["src/foo.py", "src/__pycache__/foo.pyc"],
                    diff_lines=12, created_at=_dt(4),
                    metadata={"note": f"key={LEAK}"})
    hl = HumanLabel(id="label_1", review_item_id="rev_1", task_id="task_a",
                    attempt_id="att_1", verdict=HumanVerdict.PASS, score=0.95,
                    reason=f"looks good {LEAK}", created_at=_dt(25))
    return ExhaustBundle(
        tasks=[task_a, task_b], traces=[tr], evaluations=[ev],
        human_labels=[hl], routing_decisions=[dec], rewards=[reward],
    )


def test_builders_produce_valid_examples() -> None:
    factory = DatasetFactory()
    for kind in ("routing", "human_review", "evaluator", "repair"):
        res = factory.build(kind, _bundle())
        assert all(isinstance(ex, TrainingExample) for ex in res.examples)
        assert res.version.kind == kind
        assert res.version.n_examples == len(res.examples)
        for ex in res.examples:
            TrainingExample.model_validate(ex.model_dump(mode="json"))


def test_stub_kinds_return_empty_with_note() -> None:
    factory = DatasetFactory()
    res = factory.build("viability", _bundle())
    assert res.examples == []
    assert any("stub" in n for n in res.card.notes)


def test_temporal_and_repo_split_deterministic() -> None:
    factory = DatasetFactory()
    cfg = DatasetBuildConfig(kind="human_review", temporal_split_at=_dt(10),
                             repo_holdout=["repo_holdout"])
    r1 = factory.build("human_review", _bundle(), cfg)
    r2 = factory.build("human_review", _bundle(), cfg)
    splits1 = {ex.task_id: ex.split for ex in r1.examples}
    splits2 = {ex.task_id: ex.split for ex in r2.examples}
    assert splits1 == splits2
    # human label created day 25 (>= split day 10) on repo_x => test
    assert splits1["task_a"] == "test"


def test_repo_holdout_routes_to_holdout() -> None:
    task = Task(id="task_b", repo_id="repo_holdout", title="b", created_at=_dt(1))
    hl = HumanLabel(review_item_id="r", task_id="task_b", verdict=HumanVerdict.PASS,
                    score=0.9, created_at=_dt(1))
    bundle = ExhaustBundle(tasks=[task], human_labels=[hl])
    cfg = DatasetBuildConfig(kind="human_review", repo_holdout=["repo_holdout"])
    res = DatasetFactory().build("human_review", bundle, cfg)
    assert res.examples[0].split == "holdout"
    assert res.leakage.repo_holdout_violations == 0


def test_dedup_removes_duplicates() -> None:
    hl = HumanLabel(review_item_id="r", task_id="task_a", attempt_id="att_1",
                    verdict=HumanVerdict.PASS, score=0.9, created_at=_dt(1))
    dup = hl.model_copy(update={"id": "label_dup"})
    task = Task(id="task_a", repo_id="repo_x", title="a", created_at=_dt(1))
    bundle = ExhaustBundle(tasks=[task], human_labels=[hl, dup])
    res = DatasetFactory().build("human_review", bundle)
    assert len(res.examples) == 1


def test_redaction_removes_planted_secret() -> None:
    res = DatasetFactory().build("repair", _bundle())
    blob = "".join(ex.canonical_json() for ex in res.examples)
    assert LEAK not in blob
    res2 = DatasetFactory().build("human_review", _bundle())
    blob2 = "".join(ex.canonical_json() for ex in res2.examples)
    assert LEAK not in blob2


def test_generated_files_filtered() -> None:
    assert filter_generated_files(
        ["src/a.py", "src/__pycache__/x.pyc", "node_modules/q.js", "dist/o.js"]
    ) == ["src/a.py"]
    res = DatasetFactory().build("repair", _bundle())
    target = res.examples[0].target
    # changed_files is reduced to basenames by redact_report; generated files dropped.
    assert "foo.pyc" not in target["changed_files"]
    assert "foo.py" in target["changed_files"]


def test_leakage_audit_zero_survivors() -> None:
    res = DatasetFactory().build("human_review", _bundle())
    assert res.leakage.secret_survivors == 0
    assert res.leakage.clean
    assert res.leakage.train_test_id_overlap == 0


def test_exporters_write_jsonl_no_leak(tmp_path) -> None:
    res = DatasetFactory().build("evaluator", _bundle())
    oai = tmp_path / "oai.jsonl"
    hf = tmp_path / "hf.jsonl"
    n1 = export_openai_jsonl(res.examples, oai)
    n2 = export_hf_sft_jsonl(res.examples, hf)
    assert n1 == n2 == len(res.examples)
    for p in (oai, hf):
        text = p.read_text()
        assert LEAK not in text
        assert text.count("\n") == len(res.examples)


def test_candidate_report_splits_and_recommend() -> None:
    factory = DatasetFactory()
    examples_by_kind = {
        k: factory.build(k, _bundle()).examples
        for k in ("routing", "human_review", "evaluator", "repair")
    }
    rep = build_candidate_report(examples_by_kind, min_examples=2)
    assert rep["recommend_finetune"] is True
    assert rep["secret_audit"]["clean"] is True
    assert "human_review" in rep["per_kind"]
    assert 0.0 <= rep["baseline_majority_accuracy"] <= 1.0

    rep_hi = build_candidate_report(examples_by_kind, min_examples=10_000)
    assert rep_hi["recommend_finetune"] is False


def test_lora_smoke_gating() -> None:
    assert isinstance(available(), bool)
    if not available():
        with pytest.raises(TrainingDepsUnavailable, match="training deps unavailable"):
            run_smoke("nonexistent.jsonl", "/tmp/out_acp_lora")
