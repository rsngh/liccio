"""Sample-adequacy classification (Alpha 25+ item 4)."""

from __future__ import annotations

from acp.routing.sample_adequacy import cell_adequacy, matrix_adequacy


def test_large_tight_cell_is_robust() -> None:
    a = cell_adequacy(cell_key="openai/bugfix/low", successes=45, n_conclusive=50)
    assert a.tier == "robust" and a.ci_width <= 0.25


def test_small_cell_is_directional_or_insufficient() -> None:
    assert cell_adequacy(cell_key="x", successes=8, n_conclusive=8).tier in (
        "directional", "insufficient")
    assert cell_adequacy(cell_key="x", successes=3, n_conclusive=3).tier == "insufficient"


def test_wide_interval_blocks_robust_even_at_threshold_n() -> None:
    # n=20 at 0.5 has a wide interval -> directional, not robust
    a = cell_adequacy(cell_key="x", successes=10, n_conclusive=20)
    assert a.ci_width > 0.25 and a.tier == "directional"


def test_matrix_adequacy_summarizes_tiers() -> None:
    cells = [
        {"agent_class": "openai_harness", "task_type": "bugfix", "risk_level": "low",
         "success_rate": 0.9, "conclusive_sample_size": 50},
        {"agent_class": "openai_harness", "task_type": "docs", "risk_level": "low",
         "success_rate": 1.0, "conclusive_sample_size": 3},
        {"agent_class": "fake", "task_type": "bugfix", "risk_level": "low",
         "success_rate": 0.0, "conclusive_sample_size": 0},  # ignored (no signal)
    ]
    out = matrix_adequacy(cells)
    assert out["n_cells"] == 2  # the 0-sample cell dropped
    assert out["by_tier"].get("robust", 0) == 1
    assert 0.0 <= out["robust_fraction"] <= 1.0
