"""Context-strategy benchmark (Alpha 6, WS5).

Sweeps a list of retrieval strategies over multiple synthetic repo fixtures,
computes recall@k / MRR / token-cost / latency against gold files per
(repo, strategy), and reports which strategy wins per repo plus an overall
ranking. This lets routing choose a *context strategy*, not just an agent.

Reuses the single-strategy machinery in ``retrieval_benchmark`` (the synthetic
repo generators and ``run_benchmark``). Runs fully offline using the default
hashing embedder (no network / API key required).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from acp.context.retrieval import STRATEGIES
from acp.evaluation.retrieval_benchmark import (
    BenchmarkReport,
    GoldTask,
    generate_adversarial_repo,
    generate_synthetic_repo,
    run_benchmark,
)

# Default strategies to sweep. A representative spread across the available
# retrieval strategies (see acp.context.retrieval.STRATEGIES).
DEFAULT_STRATEGIES: tuple[str, ...] = (
    "hybrid_keyword_embedding",
    "keyword_only",
    "embedding_only",
    "test_focused",
    "minimal",
)


@dataclass
class RepoFixture:
    """A named synthetic repo plus its gold tasks, built into a temp dir."""

    name: str
    generator: Callable[[Path, int, int], list[GoldTask]]
    n_files: int = 80
    seed: int = 0


def default_fixtures() -> list[RepoFixture]:
    """At least three DISTINCT fixtures so "best strategy differs by repo" is
    demonstrable: a small clean repo, a larger clean repo, and an adversarial
    repo full of decoys/secrets."""
    return [
        RepoFixture(name="small_clean", generator=generate_synthetic_repo, n_files=40, seed=1),
        RepoFixture(name="large_clean", generator=generate_synthetic_repo, n_files=160, seed=2),
        RepoFixture(name="adversarial", generator=generate_adversarial_repo, n_files=120, seed=3),
    ]


@dataclass
class StrategyResult:
    """Aggregated metrics for one (repo, strategy) pair."""

    repo: str
    strategy: str
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    mrr: float = 0.0
    token_estimate: float = 0.0
    latency_s: float = 0.0
    secret_leakage_count: int = 0

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "strategy": self.strategy,
            "recall_at_5": round(self.recall_at_5, 4),
            "recall_at_10": round(self.recall_at_10, 4),
            "mrr": round(self.mrr, 4),
            "token_estimate": round(self.token_estimate, 1),
            "latency_s": round(self.latency_s, 4),
            "secret_leakage_count": self.secret_leakage_count,
        }

    def sort_key(self) -> tuple[float, float, float, float]:
        """Higher recall@10, then MRR, then recall@5, then lower tokens wins."""
        return (self.recall_at_10, self.mrr, self.recall_at_5, -self.token_estimate)


def _result_from_report(repo: str, strategy: str, rep: BenchmarkReport) -> StrategyResult:
    return StrategyResult(
        repo=repo,
        strategy=strategy,
        recall_at_5=rep.recall_at_5,
        recall_at_10=rep.recall_at_10,
        mrr=rep.mrr,
        token_estimate=rep.avg_tokens,
        latency_s=rep.avg_latency_s,
        secret_leakage_count=rep.secret_leakage_count,
    )


@dataclass
class ContextStrategyReport:
    """Full sweep result: every (repo, strategy) pair plus per-repo winners and
    an overall strategy ranking averaged across repos."""

    strategies: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    results: list[StrategyResult] = field(default_factory=list)
    best_per_repo: dict[str, str] = field(default_factory=dict)
    overall_ranking: list[dict] = field(default_factory=list)

    def result_for(self, repo: str, strategy: str) -> StrategyResult | None:
        return next(
            (r for r in self.results if r.repo == repo and r.strategy == strategy), None
        )

    @property
    def total_secret_leakage(self) -> int:
        return sum(r.secret_leakage_count for r in self.results)

    def to_dict(self) -> dict:
        return {
            "strategies": list(self.strategies),
            "repos": list(self.repos),
            "results": [r.to_dict() for r in self.results],
            "best_per_repo": dict(self.best_per_repo),
            "overall_ranking": self.overall_ranking,
            "total_secret_leakage": self.total_secret_leakage,
        }


def _compute_overall_ranking(
    strategies: Sequence[str], results: list[StrategyResult]
) -> list[dict]:
    """Rank strategies by mean recall@10 then mean MRR across all repos."""
    ranking: list[dict] = []
    for strat in strategies:
        rows = [r for r in results if r.strategy == strat]
        if not rows:
            continue
        n = len(rows)
        ranking.append({
            "strategy": strat,
            "mean_recall_at_5": round(sum(r.recall_at_5 for r in rows) / n, 4),
            "mean_recall_at_10": round(sum(r.recall_at_10 for r in rows) / n, 4),
            "mean_mrr": round(sum(r.mrr for r in rows) / n, 4),
            "mean_token_estimate": round(sum(r.token_estimate for r in rows) / n, 1),
            "mean_latency_s": round(sum(r.latency_s for r in rows) / n, 4),
        })
    ranking.sort(
        key=lambda d: (d["mean_recall_at_10"], d["mean_mrr"], d["mean_recall_at_5"]),
        reverse=True,
    )
    return ranking


def run_context_strategy_benchmark(
    fixtures: list[RepoFixture] | None = None,
    strategies: Sequence[str] | None = None,
) -> ContextStrategyReport:
    """Sweep ``strategies`` over ``fixtures``, aggregating per (repo, strategy).

    Builds each fixture into its own temp directory, runs the existing
    single-strategy ``run_benchmark`` for every strategy, then selects the best
    strategy per repo (by recall@10, then MRR) and an overall ranking.
    """
    fixtures = fixtures or default_fixtures()
    strats = tuple(strategies) if strategies is not None else DEFAULT_STRATEGIES
    unknown = [s for s in strats if s not in STRATEGIES]
    if unknown:
        raise ValueError(f"unknown strategies: {unknown}; valid: {STRATEGIES}")

    report = ContextStrategyReport(strategies=list(strats))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for fx in fixtures:
            report.repos.append(fx.name)
            repo_path = root / fx.name
            gold = fx.generator(repo_path, fx.n_files, fx.seed)
            repo_results: list[StrategyResult] = []
            for strat in strats:
                rep = run_benchmark(repo_path, gold, strategy=strat)
                res = _result_from_report(fx.name, strat, rep)
                report.results.append(res)
                repo_results.append(res)
            best = max(repo_results, key=lambda r: r.sort_key())
            report.best_per_repo[fx.name] = best.strategy

    report.overall_ranking = _compute_overall_ranking(strats, report.results)
    return report


def report_to_markdown(report: ContextStrategyReport) -> str:
    """Render a human-readable per-repo and overall summary."""
    lines = ["# Context-strategy benchmark", ""]
    lines.append(f"- strategies: {', '.join(report.strategies)}")
    lines.append(f"- repos: {', '.join(report.repos)}")
    lines.append(f"- total secret leakage: {report.total_secret_leakage}")
    lines.append("")

    lines.append("## Best strategy per repo")
    lines.append("")
    for repo, strat in report.best_per_repo.items():
        res = report.result_for(repo, strat)
        suffix = ""
        if res is not None:
            suffix = f" (recall@10={round(res.recall_at_10, 3)}, mrr={round(res.mrr, 3)})"
        lines.append(f"- **{repo}** -> `{strat}`{suffix}")
    lines.append("")

    lines.append("## Per (repo, strategy)")
    lines.append("")
    lines.append("| repo | strategy | recall@5 | recall@10 | mrr | tokens | latency_s | leak |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in report.results:
        d = r.to_dict()
        lines.append(
            f"| {d['repo']} | {d['strategy']} | {d['recall_at_5']} | {d['recall_at_10']} "
            f"| {d['mrr']} | {d['token_estimate']} | {d['latency_s']} "
            f"| {d['secret_leakage_count']} |"
        )
    lines.append("")

    lines.append("## Overall ranking (mean across repos)")
    lines.append("")
    lines.append("| rank | strategy | recall@5 | recall@10 | mrr | tokens | latency_s |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for i, row in enumerate(report.overall_ranking, start=1):
        lines.append(
            f"| {i} | {row['strategy']} | {row['mean_recall_at_5']} "
            f"| {row['mean_recall_at_10']} | {row['mean_mrr']} "
            f"| {row['mean_token_estimate']} | {row['mean_latency_s']} |"
        )
    return "\n".join(lines)
