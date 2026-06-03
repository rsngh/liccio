"""Operator API surface (Alpha 11, WS16/WS17)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from acp.api.app import create_app
from acp.api.service import AppService
from acp.core.config import ACPSettings


def _client(tmp_path) -> TestClient:
    svc = AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'op.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))
    return TestClient(create_app(svc))


def test_operator_health_and_matrix(tmp_path) -> None:
    c = _client(tmp_path)
    h = c.get("/operator/health/control-plane", params={"mode": "production"})
    assert h.status_code == 200
    body = h.json()
    assert body["mode"] == "production" and "production_gates" in body

    m = c.get("/operator/capability-matrix")
    assert m.status_code == 200 and "n_cells" in m.json()


def test_operator_dossier_404_and_reports(tmp_path) -> None:
    c = _client(tmp_path)
    assert c.get("/operator/runs/nope/policy-dossier").status_code == 404
    listed = c.get("/operator/reports")
    assert listed.status_code == 200 and "reports" in listed.json()
