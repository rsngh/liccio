"""Production shadow mode (Alpha 26)."""

from __future__ import annotations

from acp.orchestration.shadow_mode import (
    ShadowRun,
    TaskContext,
    production_shadow_report,
    recommend,
)
from acp.routing.capability_matrix import CapabilityCell, CapabilityMatrix


def _matrix():
    m = CapabilityMatrix()
    cell = CapabilityCell("bugfix", "low", "unknown", "openai_harness", "hybrid", "standard",
                          success_rate=0.95, conclusive_sample_size=50, sample_size=50)
    cell.recompute_flags()
    m.add_cell(cell)
    return m


def test_shadow_never_writes() -> None:
    d = recommend(TaskContext("t1", "bugfix"), matrix=_matrix())
    assert d.autonomous_write is False
    assert d.dossier and "abstention" in d.dossier


def test_recommends_adapter_with_ci_from_matrix() -> None:
    d = recommend(TaskContext("t1", "bugfix", risk="low"), matrix=_matrix())
    assert d.recommended_adapter == "openai_harness"
    assert len(d.adapter_ci) == 2 and d.adapter_ci[0] > 0.8   # tight CI from n=50


def test_abstains_on_insufficient_evidence() -> None:
    d = recommend(TaskContext("t2", "bugfix", spec_clarity=0.2), matrix=_matrix())
    assert d.action == "ask_for_spec" and not d.dossier["evidence_sufficient"]


def test_high_reliability_picks_cheap_single() -> None:
    d = recommend(TaskContext("t3", "bugfix", single_shot_reliability=0.95), matrix=_matrix())
    assert d.recommended_compute_arm == "cheap_single"


def test_shadow_report_invariants() -> None:
    runs = [ShadowRun(recommend(TaskContext(f"t{i}", "bugfix"), matrix=_matrix()),
                      human_verdict=("accepted" if i % 2 == 0 else "rejected"))
            for i in range(4)]
    rep = production_shadow_report(runs)
    assert rep["n_runs"] == 4 and rep["n_accepted"] == 2
    assert rep["no_autonomous_writes"] and rep["every_recommendation_has_dossier"]
