"""Context retrieval benchmark tests (round-1 two-day D2B2 / §E)."""

from __future__ import annotations

from acp.evaluation.retrieval_benchmark import (
    BenchmarkReport,
    generate_synthetic_repo,
    report_to_markdown,
    run_benchmark,
)


def test_benchmark_fixture_recall_threshold(tmp_path) -> None:
    repo = tmp_path / "syn"
    gold = generate_synthetic_repo(repo, n_files=60)
    assert gold
    rep = run_benchmark(repo, gold)
    # the gold file contains the query's unique token -> high recall expected
    assert rep.recall_at_10 >= 0.8
    assert rep.mrr > 0.0


def test_benchmark_no_secret_leakage(tmp_path) -> None:
    repo = tmp_path / "syn"
    gold = generate_synthetic_repo(repo, n_files=40)
    rep = run_benchmark(repo, gold)
    assert rep.secret_leakage_count == 0


def test_benchmark_report_schema(tmp_path) -> None:
    repo = tmp_path / "syn"
    gold = generate_synthetic_repo(repo, n_files=30)
    rep = run_benchmark(repo, gold)
    d = rep.to_dict()
    for key in ("n_tasks", "recall_at_5", "recall_at_10", "mrr", "avg_tokens",
                "avg_latency_s", "duplicate_chunk_ratio", "secret_leakage_count", "per_task"):
        assert key in d
    assert isinstance(rep, BenchmarkReport)
    assert "recall@5" in report_to_markdown(rep)
