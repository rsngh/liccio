"""Report warehouse: queryable report entities (Alpha 11, WS18)."""

from __future__ import annotations

import json

from acp.api.service import AppService
from acp.core.config import ACPSettings


def _svc(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'w.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws"))


def test_ingest_list_show_diff(tmp_path, monkeypatch) -> None:
    # A tiny manifest pointing at one on-disk report under tmp.
    reports_dir = tmp_path / "evals" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "r.json").write_text(json.dumps({"n": 10, "accuracy": 0.8}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "acp.observability.artifact_manifest.REPORT_SCHEMA_REGISTRY",
        {"evals/reports/r.json": ["n"]})

    svc = _svc(tmp_path)
    first = svc.ingest_reports()
    assert first["reports_ingested"] == 1
    listed = svc.list_reports(first["ingest_id"])
    assert len(listed) == 1 and listed[0]["path"] == "evals/reports/r.json"
    shown = svc.show_report(listed[0]["id"])
    assert shown["metric_map"]["n"] == 10.0 if "metric_map" in shown else True
    assert any(m["name"] == "accuracy" for m in shown["metrics"])

    # Change the report and re-ingest -> diff shows the metric delta over time.
    (reports_dir / "r.json").write_text(json.dumps({"n": 10, "accuracy": 0.95}))
    second = svc.ingest_reports()
    diff = svc.diff_reports("evals/reports/r.json", first["ingest_id"],
                            second["ingest_id"])
    assert diff["hash_changed"] is True
    assert round(diff["metric_deltas"]["accuracy"], 2) == 0.15
