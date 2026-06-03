"""Larger mixed empirical corpus (Alpha 11, WS12)."""

from __future__ import annotations

import json

from acp.evaluation.mixed_corpus import generate_mixed_corpus


def test_test_scale_corpus_computes_all_stats() -> None:
    c = generate_mixed_corpus(scale="test")
    for key in ("n_tasks", "n_cells", "n_sufficient", "n_preference_pairs",
                "ope_overlap_estimate", "pareto_frontier_sizes", "drift_window_count",
                "mean_counterfactual_regret", "per_task_risk_coverage"):
        assert key in c, f"missing {key}"
    assert c["n_preference_pairs"] > 0
    assert c["n_tasks"] > 0


def test_corpus_json_serializable() -> None:
    c = generate_mixed_corpus(scale="test")
    json.dumps(c)  # must not raise
    assert isinstance(c["pareto_frontier_sizes"], (list, dict))
