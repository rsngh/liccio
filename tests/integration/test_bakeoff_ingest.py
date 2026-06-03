"""Ingest observed bakeoff cells into real OPE log (Alpha 11, WS14)."""

from __future__ import annotations

from acp.api.service import AppService
from acp.core.config import ACPSettings


def _svc(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'b.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def _cells() -> list[dict]:
    cells = []
    for i in range(6):
        cells.append({"task": f"bug{i}", "task_type": "bugfix",
                      "adapter": "openai_harness", "success": True})
        cells.append({"task": f"bug{i}", "task_type": "bugfix",
                      "adapter": "fake", "success": False})
    return cells


def test_ingested_cells_become_real_ope_log(tmp_path) -> None:
    svc = _svc(tmp_path)
    res = svc.ingest_bakeoff_cells(_cells())
    assert res["ingested"] == 12

    # The ingested decisions+rewards form a real OPE log the report runs on.
    real = svc.real_log_ope_report()
    assert real["n"] >= 10
    # A solver-preferring policy beats random on the observed data.
    assert "policies" in real and "greedy" in real["policies"]
    assert real["policies"]["greedy"]["dr"] >= real["policies"]["random"]["dr"]


def test_ingested_data_drives_capability_matrix(tmp_path) -> None:
    svc = _svc(tmp_path)
    svc.ingest_bakeoff_cells(_cells())
    samples = svc._ope_samples()
    assert len(samples) >= 10  # real propensity-scored log exists
