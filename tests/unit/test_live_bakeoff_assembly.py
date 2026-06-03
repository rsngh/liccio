"""Live-bakeoff assembly from observed cells (Alpha 11, WS14) — offline."""

from __future__ import annotations

from acp.evaluation.live_bakeoff import (
    assemble_capability_matrix,
    assemble_ope,
    solved_by_adapter,
)

# Cells shaped exactly like the live bakeoff emits (here from a fixed fixture so
# the assembly logic is tested without API keys).
_CELLS = [
    {"task": "t1", "task_type": "bugfix", "adapter": "openai_harness",
     "success": True, "cost_usd": 0.0006, "latency_s": 3.4, "is_harness": True,
     "context_strategy": "hybrid_keyword_embedding"},
    {"task": "t1", "task_type": "bugfix", "adapter": "fake", "success": False,
     "cost_usd": 0.0, "latency_s": 0.01, "context_strategy": "hybrid_keyword_embedding"},
    {"task": "t2", "task_type": "bugfix", "adapter": "openai_harness",
     "success": True, "cost_usd": 0.0004, "latency_s": 1.6, "is_harness": True,
     "context_strategy": "hybrid_keyword_embedding"},
    {"task": "t2", "task_type": "bugfix", "adapter": "fake", "success": False,
     "cost_usd": 0.0, "latency_s": 0.01, "context_strategy": "hybrid_keyword_embedding"},
]


def test_solved_by_adapter_counts_real_solves() -> None:
    s = solved_by_adapter(_CELLS)
    assert s["openai_harness"] == 2
    assert s["fake"] == 0


def test_capability_matrix_from_observed_cells() -> None:
    m = assemble_capability_matrix(_CELLS).to_dict()
    assert m["n_cells"] >= 1


def test_ope_from_observed_cells_ranks_solver() -> None:
    ope = assemble_ope(_CELLS)
    assert ope["source"] == "REAL observed agent runs"
    assert ope["n"] == 4
    # The harness that actually solves beats random under DR.
    assert ope["greedy_dr"]["value"] > ope["random_dr"]["value"]
    assert ope["best_adapter_per_task_type"]["bugfix"] == "openai_harness"


def test_empty_cells_safe() -> None:
    assert assemble_ope([])["n"] == 0
