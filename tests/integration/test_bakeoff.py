"""Bakeoff matrix tests (round-1 two-day D2B4)."""

from __future__ import annotations

import pytest

from acp.api.service import AppService
from acp.cli.demos import make_demo_repo
from acp.core.config import ACPSettings
from acp.evaluation.bakeoff import BakeoffConfig, bakeoff_to_markdown, run_bakeoff


@pytest.fixture
def service(tmp_path) -> AppService:
    return AppService(ACPSettings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'b.db'}",
        artifact_dir=tmp_path / "art", workspace_dir=tmp_path / "ws",
    ))


def _report(service, tmp_path):
    repo = service.create_repo("b", make_demo_repo(tmp_path / "repo"), default_branch="master")
    cfg = BakeoffConfig(
        tasks=[("bugfix", "Fix divide bug", "zero divisor")],
        strategies=["minimal", "bug_reproduction"],
        verification_policies=["standard"],
        seeds=[1],
    )
    return run_bakeoff(service, repo.id, cfg)


def test_bakeoff_report_schema(service, tmp_path) -> None:
    rep = _report(service, tmp_path)
    for key in ("config", "available_agents", "agents_used", "cells", "summary",
                "failure_taxonomy", "unavailable_real_adapters"):
        assert key in rep
    cell = rep["cells"][0]
    for key in ("task_class", "strategy", "verification", "seed", "status",
                "agent", "attempts", "cost_usd", "latency_s", "failure_class"):
        assert key in cell
    assert "Bakeoff report" in bakeoff_to_markdown(rep)


def test_bakeoff_runs_and_marks_unavailable(service, tmp_path) -> None:
    rep = _report(service, tmp_path)
    # patch/fake available; real adapters recorded as unavailable
    assert set(rep["available_agents"]) >= {"patch", "fake"}
    assert "claude" in rep["unavailable_real_adapters"]


def test_bakeoff_has_failure_taxonomy(service, tmp_path) -> None:
    rep = _report(service, tmp_path)
    assert isinstance(rep["failure_taxonomy"], dict)
    assert sum(rep["failure_taxonomy"].values()) == rep["summary"]["cells"]
