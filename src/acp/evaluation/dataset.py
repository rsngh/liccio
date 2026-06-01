"""No-patch dataset loader (round-5 WS5).

Loads ``evals/datasets/no_patch_tasks.yaml`` into typed ``DatasetTask`` records
and enforces the central invariant: no task may carry a pre-supplied patch
(``metadata.files`` / ``metadata.patch``). Each task names a fixture generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from acp.evaluation.fixtures import FIXTURES


@dataclass
class DatasetTask:
    key: str
    task_type: str
    risk: str
    fixture: str
    title: str
    body: str
    acceptance: list[str] = field(default_factory=list)
    expected_human_review: bool = False
    metadata: dict = field(default_factory=dict)


def _validate(task: DatasetTask) -> None:
    if "files" in task.metadata or "patch" in task.metadata:
        raise ValueError(
            f"no-patch task {task.key!r} must not carry metadata.files/metadata.patch")
    if task.fixture not in FIXTURES:
        raise ValueError(f"task {task.key!r} references unknown fixture {task.fixture!r}")


def load_dataset(path: str | Path) -> list[DatasetTask]:
    import yaml

    data = yaml.safe_load(Path(path).read_text()) or {}
    tasks = [DatasetTask(**t) for t in data.get("tasks", [])]
    seen: set[str] = set()
    for t in tasks:
        if t.key in seen:
            raise ValueError(f"duplicate task key {t.key!r}")
        seen.add(t.key)
        _validate(t)
    return tasks


def dataset_summary(tasks: list[DatasetTask]) -> dict:
    by_type: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for t in tasks:
        by_type[t.task_type] = by_type.get(t.task_type, 0) + 1
        by_risk[t.risk] = by_risk.get(t.risk, 0) + 1
    return {"n": len(tasks), "by_task_type": by_type, "by_risk": by_risk,
            "fixtures": sorted({t.fixture for t in tasks})}
