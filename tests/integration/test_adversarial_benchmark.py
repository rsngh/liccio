"""Adversarial retrieval benchmark (round-2 Block G)."""

from __future__ import annotations

from acp.evaluation.retrieval_benchmark import (
    compare_strategies,
    generate_adversarial_repo,
    run_benchmark,
)


def test_adversarial_no_secret_leakage(tmp_path) -> None:
    repo = tmp_path / "adv"
    gold = generate_adversarial_repo(repo, n_files=60)
    assert gold
    rep = run_benchmark(repo, gold)
    assert rep.secret_leakage_count == 0


def test_adversarial_reports_decoy_rate(tmp_path) -> None:
    repo = tmp_path / "adv"
    gold = generate_adversarial_repo(repo, n_files=40)
    rep = run_benchmark(repo, gold)
    d = rep.to_dict()
    assert "false_positive_decoy_rate" in d
    assert 0.0 <= d["false_positive_decoy_rate"] <= 1.0
    # gold file (carries the unique token) should still be findable despite decoys
    assert rep.recall_at_10 >= 0.7


def test_hybrid_beats_or_matches_single_signal(tmp_path) -> None:
    repo = tmp_path / "adv"
    gold = generate_adversarial_repo(repo, n_files=60)
    results = compare_strategies(repo, gold)
    hybrid = results["hybrid_keyword_embedding"]
    kw = results["keyword_only"]
    emb = results["embedding_only"]
    # hybrid is at least as good as either single signal on recall@10
    assert hybrid.recall_at_10 >= kw.recall_at_10 - 1e-9
    assert hybrid.recall_at_10 >= emb.recall_at_10 - 1e-9
    # and no strategy leaks secrets
    assert all(r.secret_leakage_count == 0 for r in results.values())
