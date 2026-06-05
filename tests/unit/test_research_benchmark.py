"""Research-engineering benchmark hardening (Alpha 24 area 15)."""

from __future__ import annotations

from acp.evaluation.research_benchmark import (
    ResearchTask,
    classify_change,
    research_progress,
    research_routing,
    run_research_benchmark,
)


def test_change_classification() -> None:
    assert classify_change(["learning_rate", "batch_size"]) == "hyperparameter_tuning"
    assert classify_change(["compute_loss", "attention_forward"]) == "algorithmic"
    assert classify_change(["lr", "value_head"]) == "mixed"
    assert classify_change(["readme"]) == "unknown"


def test_tuning_only_reward_is_capped() -> None:
    task = ResearchTask("t", "improve_architecture", baseline_metric=0.5,
                        human_target_metric=1.0)
    # achieved 0.9 -> recovered 0.8, but via tuning only -> reward capped at 0.2
    tuned = research_progress(task, 0.9, ["learning_rate"])
    assert tuned.recovered_fraction == 0.8 and tuned.reward == 0.2 and not tuned.substantive
    # same gain via an algorithmic change -> full reward
    algo = research_progress(task, 0.9, ["attention_forward"])
    assert algo.reward == 0.8 and algo.substantive


def test_recovered_fraction_floored_at_zero() -> None:
    task = ResearchTask("t", "ablate_idea", 0.5, 1.0)
    assert research_progress(task, 0.4, ["loss"]).recovered_fraction == 0.0  # regressed


def test_research_tasks_route_to_heavy_machinery() -> None:
    r = research_routing(ResearchTask("t", "alphazero_loop", 0.0, 1.0))
    assert r["consult_advisor"] and r["heavy_skill"] and r["topology_search"]
    b = research_routing(ResearchTask("b", "bugfix", 0.0, 1.0))
    assert not b["consult_advisor"] and b["strict_verification"]


def test_benchmark_distinguishes_algorithmic_from_tuning() -> None:
    task = ResearchTask("t1", "improve_architecture", 0.5, 1.0)
    recs = [
        (task, 0.9, ["attention_forward"]),     # substantive
        (ResearchTask("t2", "ablate_idea", 0.5, 1.0), 0.9, ["learning_rate"]),  # tuning
    ]
    rep = run_research_benchmark(recs)
    assert rep.n_substantive == 1 and rep.n_tuning_only == 1
    assert rep.routes_research_differently
    assert rep.mean_reward < rep.mean_recovered  # tuning cap pulls reward below raw recovery
