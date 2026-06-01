"""FastAPI endpoint tests (charter §18)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from acp.api.app import create_app
from acp.api.service import AppService
from acp.core.config import ACPSettings


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
        artifact_dir=tmp_path / "art",
        workspace_dir=tmp_path / "ws",
    )
    return TestClient(create_app(AppService(settings)))


def test_health_and_version(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert "version" in client.get("/version").json()


def test_openapi_schema(client) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "agent-control-plane"
    assert "/tasks" in schema["paths"]


def test_task_create_and_get(client) -> None:
    repo = client.post("/repos", json={"name": "r", "local_path": "/tmp/x"}).json()
    resp = client.post("/tasks", json={"repo_id": repo["id"], "title": "fix bug"})
    assert resp.status_code == 201
    task = resp.json()
    got = client.get(f"/tasks/{task['id']}")
    assert got.status_code == 200
    assert got.json()["title"] == "fix bug"


def test_invalid_id_404(client) -> None:
    assert client.get("/tasks/nope").status_code == 404
    assert client.get("/repos/nope").status_code == 404
    assert client.get("/runs/nope").status_code == 404


def test_invalid_payload_422(client) -> None:
    assert client.post("/tasks", json={"title": "missing repo_id"}).status_code == 422


def test_run_via_api(client, tmp_path) -> None:
    from git import Repo

    src = tmp_path / "demo"
    src.mkdir()
    (src / "calculator.py").write_text("def divide(a, b):\n    return 0\n")
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add(["calculator.py"])
    repo.index.commit("init")

    r = client.post("/repos", json={"name": "demo", "local_path": str(src),
                    "default_branch": "master"}).json()
    fixed = "def divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError\n    return a / b\n"
    t = client.post(
        "/tasks",
        json={"repo_id": r["id"], "title": "Fix divide", "body": "raise on zero",
              "metadata": {"files": {"calculator.py": fixed}}},
    ).json()
    run = client.post(f"/tasks/{t['id']}/run").json()
    assert run["status"] in ("succeeded", "failed", "waiting_for_human")
    state = client.get(f"/runs/{run['run_id']}/state")
    assert state.status_code == 200


def test_policies_endpoint(client) -> None:
    assert client.get("/policies").status_code == 200
