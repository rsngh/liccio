"""Context retrieval quality benchmark (round-1 two-day D2B2).

Generates synthetic repos with known "gold" files per task, compiles context
packs, and measures recall@k, MRR, token count, compile latency, duplicate-chunk
ratio, and secret leakage. Importable core + a thin CLI script wrap it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from acp.context.compiler import ContextCompiler
from acp.schemas.task import Task


@dataclass
class GoldTask:
    title: str
    query: str
    gold_paths: list[str]
    task_type: str = "bugfix"


def generate_synthetic_repo(root: Path, n_files: int = 200, seed: int = 0) -> list[GoldTask]:
    """Create a synthetic repo and return gold tasks pointing at known files."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "synthetic"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
    )
    # decoy secret + binary that must never be retrieved
    (root / ".env").write_text("ACP_OPENAI_API_KEY=sk-must-not-leak-000")
    (root / "blob.bin").write_bytes(b"\x00\x01\x02" * 64)

    gold: list[GoldTask] = []
    for i in range(n_files):
        pkg = root / f"pkg{i % 25}"
        pkg.mkdir(exist_ok=True)
        rel = f"pkg{i % 25}/mod{i}.py"
        (root / rel).write_text(
            f"def feature_{i}(x):\n    # unique token zorp{i}\n    return x + {i}\n\n\n"
            f"class Widget{i}:\n    value = {i}\n"
        )
        # one gold task per ~10 files keeps the dataset small but representative
        if i % 10 == 0:
            gold.append(GoldTask(
                title=f"Fix feature_{i}",
                query=f"feature_{i} zorp{i} returns wrong value bug",
                gold_paths=[rel],
            ))
    return gold


@dataclass
class BenchmarkReport:
    n_tasks: int = 0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    mrr: float = 0.0
    avg_tokens: float = 0.0
    avg_latency_s: float = 0.0
    duplicate_chunk_ratio: float = 0.0
    secret_leakage_count: int = 0
    per_task: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "n_tasks": self.n_tasks,
            "recall_at_5": round(self.recall_at_5, 4),
            "recall_at_10": round(self.recall_at_10, 4),
            "mrr": round(self.mrr, 4),
            "avg_tokens": round(self.avg_tokens, 1),
            "avg_latency_s": round(self.avg_latency_s, 4),
            "duplicate_chunk_ratio": round(self.duplicate_chunk_ratio, 4),
            "secret_leakage_count": self.secret_leakage_count,
            "per_task": self.per_task,
        }


def _ranked_paths(items) -> list[str]:
    seen, order = set(), []
    for it in items:
        if it.path not in seen:
            seen.add(it.path)
            order.append(it.path)
    return order


def run_benchmark(
    repo_path: Path, tasks: list[GoldTask], strategy: str = "hybrid_keyword_embedding"
) -> BenchmarkReport:
    rep = BenchmarkReport(n_tasks=len(tasks))
    r5 = r10 = mrr = tokens = latency = dup = 0.0
    leak = 0
    for gt in tasks:
        task = Task(repo_id="bench", title=gt.title, body=gt.query, task_type=gt.task_type)
        t0 = time.monotonic()
        pack = ContextCompiler(repo_path, "bench", "snap").compile(
            task, strategy=strategy, token_budget=20_000
        )
        dt = time.monotonic() - t0
        ranked = _ranked_paths(pack.items)
        top5, top10 = ranked[:5], ranked[:10]
        hit5 = any(g in top5 for g in gt.gold_paths)
        hit10 = any(g in top10 for g in gt.gold_paths)
        rank = next((i + 1 for i, p in enumerate(ranked) if p in gt.gold_paths), 0)
        r5 += hit5
        r10 += hit10
        mrr += (1.0 / rank) if rank else 0.0
        tokens += pack.token_estimate
        latency += dt
        fps = [it.fingerprint() for it in pack.items]
        dup += (1 - len(set(fps)) / len(fps)) if fps else 0.0
        leak += sum(1 for it in pack.items if ".env" in it.path or "sk-must-not-leak" in it.content)
        rep.per_task.append({
            "task": gt.title, "gold": gt.gold_paths, "rank": rank,
            "hit@5": hit5, "hit@10": hit10, "tokens": pack.token_estimate,
        })
    n = max(1, len(tasks))
    rep.recall_at_5 = r5 / n
    rep.recall_at_10 = r10 / n
    rep.mrr = mrr / n
    rep.avg_tokens = tokens / n
    rep.avg_latency_s = latency / n
    rep.duplicate_chunk_ratio = dup / n
    rep.secret_leakage_count = leak
    return rep


def report_to_markdown(rep: BenchmarkReport) -> str:
    d = rep.to_dict()
    lines = [
        "# Context retrieval benchmark", "",
        f"- tasks: {d['n_tasks']}",
        f"- recall@5: {d['recall_at_5']}",
        f"- recall@10: {d['recall_at_10']}",
        f"- MRR: {d['mrr']}",
        f"- avg tokens: {d['avg_tokens']}",
        f"- avg latency (s): {d['avg_latency_s']}",
        f"- duplicate chunk ratio: {d['duplicate_chunk_ratio']}",
        f"- secret leakage: {d['secret_leakage_count']}",
    ]
    return "\n".join(lines)
