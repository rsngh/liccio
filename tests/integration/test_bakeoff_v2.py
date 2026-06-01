"""No-patch dataset + bakeoff engine v2 (round-5 WS5/WS6)."""

from __future__ import annotations

import pytest

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.evaluation.dataset import DatasetTask, dataset_summary, load_dataset
from acp.evaluation.fixtures import FIXTURES, build_fixture

DATASET = "evals/datasets/no_patch_tasks.yaml"


def test_dataset_loads_and_has_no_patches() -> None:
    tasks = load_dataset(DATASET)
    assert len(tasks) >= 6
    for t in tasks:
        assert "files" not in t.metadata and "patch" not in t.metadata
        assert t.fixture in FIXTURES
    summary = dataset_summary(tasks)
    # all six task types represented
    assert {"bugfix", "test_generation", "feature", "refactor",
            "security", "migration"}.issubset(set(summary["by_task_type"]))


def test_dataset_rejects_patch_metadata() -> None:
    from acp.evaluation.dataset import _validate
    bad = DatasetTask(key="x", task_type="bugfix", risk="low",
                      fixture="python_buggy_app", title="t", body="b",
                      metadata={"files": {"a.py": "x"}})
    with pytest.raises(ValueError, match="must not carry"):
        _validate(bad)


def test_all_fixtures_build(tmp_path) -> None:
    for i, name in enumerate(FIXTURES):
        root = tmp_path / f"f{i}"
        build_fixture(name, root)
        assert any(root.rglob("*.py")), f"fixture {name} produced no python files"
        assert (root / "pyproject.toml").exists()


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'v2.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_bakeoff_v2_persists_with_aggregates(service) -> None:
    run = service.run_bakeoff_v2(["patch", "fake"], DATASET, repetitions=1)
    assert run.kind == "multi_harness_v2"
    report = AppService(service.settings).get_eval_report(run.id)["content"]
    assert report["cells"], "no cells"
    # aggregates by adapter / task type / risk all present
    assert set(report["by_adapter"]) == {"patch", "fake"}
    assert "bugfix" in report["by_task_type"] and "security" in report["by_task_type"]
    assert set(report["by_risk"]).issubset({"low", "medium", "high"})
    # per-cell rich metrics present
    c = report["cells"][0]
    for field in ("tool_calls", "file_writes", "tokens", "cost_usd", "latency_s",
                  "failure_class", "task_type", "risk"):
        assert field in c


def test_bakeoff_v2_repetitions_multiply_cells(service) -> None:
    run = service.run_bakeoff_v2(["fake"], DATASET, repetitions=2)
    report = AppService(service.settings).get_eval_report(run.id)["content"]
    n_tasks = report["n_tasks"]
    # 1 adapter x n_tasks x 2 reps
    assert report["summary"]["n_cells"] == n_tasks * 2
