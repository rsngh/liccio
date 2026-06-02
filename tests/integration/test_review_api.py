"""Human-review studio product API tests (Alpha 8, WS15)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from git import Repo

from acp.api.app import create_app
from acp.api.service import AppService
from acp.core.config import ACPSettings
from acp.core.enums import RunStatus


def _settings(tmp_path) -> ACPSettings:
    return ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'r.db'}",
        artifact_dir=tmp_path / "art",
        workspace_dir=tmp_path / "ws",
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


def _client_with_open_review(tmp_path):
    svc = AppService(_settings(tmp_path))
    app = create_app(svc)
    repo = _repo(svc, tmp_path)
    fixed = "def divide(a, b):\n    return a / b\n"
    task = svc.create_task(
        repo.id, "Update auth password hashing", "auth",
        metadata={"files": {"calculator.py": fixed}},
    )
    state = svc.run_task(task.id)
    assert state.status in (RunStatus.WAITING_FOR_HUMAN, RunStatus.WAITING_FOR_HUMAN.value)
    review = svc.list_reviews()[0]
    return TestClient(app), review, task


def test_queue_lists_open_review(tmp_path) -> None:
    client, review, _task = _client_with_open_review(tmp_path)
    resp = client.get("/reviews/queue")
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()]
    assert review.id in ids
    # priority_min filters.
    filtered = client.get("/reviews/queue", params={"priority_min": review.priority + 1.0})
    assert all(i["priority"] >= review.priority + 1.0 for i in filtered.json())


def test_bundle_has_expected_keys(tmp_path) -> None:
    client, review, _task = _client_with_open_review(tmp_path)
    resp = client.get(f"/reviews/{review.id}/bundle")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("review", "uncertainty_reason", "diff_summary",
                "trace_summary", "judge_disagreement"):
        assert key in body
    assert client.get("/reviews/missing/bundle").status_code == 404


def test_label_resolves_and_resumes(tmp_path) -> None:
    client, review, task = _client_with_open_review(tmp_path)
    resp = client.post(
        f"/reviews/{review.id}/label",
        json={"verdict": "pass", "score": 0.9, "reason": "ok", "reviewer": "tester"},
    )
    assert resp.status_code == 200
    assert resp.json()["verdict"] in ("pass", "PASS")
    assert resp.json()["review_item_id"] == review.id
    # The label persisted as a durable eval case (proves label_review committed
    # and the run resumed without error).
    case = client.post(f"/reviews/{review.id}/make-eval-case")
    assert case.status_code == 200
    assert case.json()["case"]["verdict"] in ("pass", "PASS")
    assert client.post("/reviews/missing/label", json={}).status_code == 404


def test_make_eval_case_and_training_example(tmp_path) -> None:
    client, review, task = _client_with_open_review(tmp_path)
    client.post(f"/reviews/{review.id}/label", json={"verdict": "pass", "score": 0.9})

    case_resp = client.post(f"/reviews/{review.id}/make-eval-case")
    assert case_resp.status_code == 200
    assert case_resp.json()["case"]["task_id"] == task.id

    te_resp = client.post(f"/reviews/{review.id}/make-training-example")
    assert te_resp.status_code == 200
    te = te_resp.json()["training_example"]
    assert te["dataset_kind"] == "human_review"
    assert te["task_id"] == task.id


def test_make_eval_case_without_label_is_400(tmp_path) -> None:
    client, review, _task = _client_with_open_review(tmp_path)
    assert client.post(f"/reviews/{review.id}/make-eval-case").status_code == 400


def test_calibrate_returns_trust_view(tmp_path) -> None:
    client, review, _task = _client_with_open_review(tmp_path)
    resp = client.post(f"/reviews/{review.id}/calibrate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_id"] == review.id
    assert "trust" in body
    assert body["trust"]["n_cases"] > 0
