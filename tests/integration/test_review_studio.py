"""Human-review studio backend (Alpha 6, WS6)."""

from __future__ import annotations

from git import Repo

from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import HumanVerdict, RunStatus
from acp.schemas.human_review import HumanLabel


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'r.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    )


def _repo(svc, tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    (src / "pyproject.toml").write_text(
        '[project]\nname = "c"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    r = Repo.init(src)
    r.config_writer().set_value("user", "name", "t").release()
    r.config_writer().set_value("user", "email", "t@e.com").release()
    r.index.add(["calculator.py", "pyproject.toml"])
    r.index.commit("init")
    return svc.create_repo("c", str(src), default_branch="master")


def _open_review(tmp_path):
    settings = _settings(tmp_path)
    svc = AppService(settings)
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    # High-risk auth task routes to human review.
    task = svc.create_task(repo.id, "Update auth password hashing", "auth",
                          metadata={"files": {"calculator.py": fixed}})
    state = svc.run_task(task.id)
    assert state.status in (RunStatus.WAITING_FOR_HUMAN, RunStatus.WAITING_FOR_HUMAN.value)
    return svc, task, state


def test_bundle_is_complete_and_secret_free(tmp_path) -> None:
    svc, task, state = _open_review(tmp_path)
    review = svc.list_reviews()[0]
    bundle = svc.review_bundle(review.id)
    assert bundle["review"]["id"] == review.id
    assert "uncertainty_reason" in bundle
    assert "diff_summary" in bundle
    assert "trace_summary" in bundle
    assert "judge_disagreement" in bundle
    # No secrets / raw prompts in the bundle.
    import json
    blob = json.dumps(bundle)
    assert "api_key" not in blob.lower() or "[REDACTED]" in blob


def test_priority_filter_and_sort(tmp_path) -> None:
    svc, task, state = _open_review(tmp_path)
    high = svc.list_reviews(priority_min=0.0)
    assert high  # at least the one we created
    # Sorted by priority descending.
    prios = [i.priority for i in high]
    assert prios == sorted(prios, reverse=True)


def test_label_becomes_eval_case(tmp_path) -> None:
    svc, task, state = _open_review(tmp_path)
    review = svc.list_reviews()[0]
    label = HumanLabel(review_item_id=review.id, task_id=task.id,
                       verdict=HumanVerdict.PASS, score=0.9, reason="looks correct")
    svc.label_review(review.id, label)
    result = svc.make_eval_case(review.id)
    assert result["case"]["task_id"] == task.id
    assert result["case"]["source"] == "human_review"
    assert result["case"]["verdict"] in ("pass", "PASS")

    # WS9: the same label becomes a redacted training example.
    te = svc.make_training_example(review.id)["training_example"]
    assert te["dataset_kind"] == "human_review"
    assert te["task_id"] == task.id
    assert te["label_source"] == "human"
    assert te["target"] in ("pass", "PASS")
