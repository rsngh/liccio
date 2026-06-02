"""Context-strategy benchmark tests (Alpha 6, WS5)."""

from __future__ import annotations

import json

from acp.evaluation.context_strategy_benchmark import (
    ContextStrategyReport,
    default_fixtures,
    run_context_strategy_benchmark,
)

STRATS = ("hybrid_keyword_embedding", "keyword_only", "test_focused")


def _small_report() -> ContextStrategyReport:
    # Tiny fixtures keep the offline sweep fast while exercising every path.
    fixtures = default_fixtures()
    for fx in fixtures:
        fx.n_files = 30
    return run_context_strategy_benchmark(fixtures=fixtures, strategies=STRATS)


def test_sweep_returns_result_per_repo_strategy() -> None:
    report = _small_report()
    repos = report.repos
    assert len(repos) >= 3
    assert len(report.results) == len(repos) * len(STRATS)
    for repo in repos:
        for strat in STRATS:
            assert report.result_for(repo, strat) is not None


def test_each_result_has_all_metrics() -> None:
    report = _small_report()
    for r in report.results:
        assert 0.0 <= r.recall_at_5 <= 1.0
        assert 0.0 <= r.recall_at_10 <= 1.0
        assert 0.0 <= r.mrr <= 1.0
        assert r.token_estimate >= 0.0
        assert r.latency_s >= 0.0


def test_best_strategy_selected_per_repo() -> None:
    report = _small_report()
    for repo in report.repos:
        best = report.best_per_repo.get(repo)
        assert best in STRATS
        # The selected winner must dominate by the documented sort key.
        chosen = report.result_for(repo, best)
        assert chosen is not None
        repo_results = [r for r in report.results if r.repo == repo]
        assert chosen.sort_key() == max(r.sort_key() for r in repo_results)


def test_overall_ranking_is_ordered() -> None:
    report = _small_report()
    assert len(report.overall_ranking) == len(STRATS)
    keys = [(d["mean_recall_at_10"], d["mean_mrr"]) for d in report.overall_ranking]
    assert keys == sorted(keys, reverse=True)


def test_report_dict_is_json_serializable() -> None:
    report = _small_report()
    blob = json.dumps(report.to_dict())
    restored = json.loads(blob)
    assert "best_per_repo" in restored
    assert "overall_ranking" in restored
    assert "results" in restored


def test_no_secret_leakage() -> None:
    report = _small_report()
    assert report.total_secret_leakage == 0
    for r in report.results:
        assert r.secret_leakage_count == 0
