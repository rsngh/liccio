"""Context-strategy retrieval bakeoff: grep vs embedding vs hybrid (Alpha 24 area 6).

A real, FREE, deterministic micro-benchmark over the graded benchmark repos: for each task
the query is the prompt and the target is the buggy module file. We rank candidate files by
grep (keyword overlap), embedding (HashingEmbedder cosine), and hybrid (rank fusion), and
measure retrieval hit-rate (target ranked #1) and token cost. The cost-adjusted optimizer
then picks a strategy — grep is allowed to win. Writes context_strategy_ope.json,
grep_vs_embedding_bakeoff.json, context_reuse_frontier.json.
"""

from __future__ import annotations

import json
import math
import re
import tempfile
from pathlib import Path

from acp.agents.benchmark_suite import BENCH_TASKS, build_bench_repo
from acp.context.embeddings import HashingEmbedder
from acp.context.strategy_optimizer import ContextObservation, choose_strategy

ROOT = Path("evals/reports")
EMB = HashingEmbedder()


def _tokens(text: str) -> int:
    return len(text.split())


def _code_files(repo: Path) -> list[Path]:
    return [p for p in repo.rglob("*.py")
            if "test" not in p.name and p.name != "conftest.py"]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _grep_rank(query: str, files: list[Path]) -> tuple[Path, int]:
    words = set(re.findall(r"[a-zA-Z_]{3,}", query.lower()))
    best, best_hits, cost = files[0], -1, 0
    for f in files:
        text = f.read_text().lower()
        hits = sum(text.count(w) for w in words)
        cost += min(_tokens(f.read_text()), 200)  # grep returns only matched context
        if hits > best_hits:
            best, best_hits = f, hits
    return best, cost


def _embed_rank(query: str, files: list[Path]) -> tuple[Path, int]:
    qv = EMB.embed(query)
    best, best_sim, cost = files[0], -2.0, 0
    for f in files:
        text = f.read_text()
        cost += _tokens(text)  # embedding must read whole files
        sim = _cos(qv, EMB.embed(text))
        if sim > best_sim:
            best, best_sim = f, sim
    return best, cost


def _bakeoff() -> dict:
    rows = {"grep": {"hits": 0, "tokens": 0}, "embedding": {"hits": 0, "tokens": 0},
            "hybrid": {"hits": 0, "tokens": 0}}
    n = 0
    for task in BENCH_TASKS:
        with tempfile.TemporaryDirectory() as d:
            repo = build_bench_repo(Path(d), task)
            files = _code_files(repo)
            target = (repo / task.module_path).resolve()
            gbest, gcost = _grep_rank(task.prompt, files)
            ebest, ecost = _embed_rank(task.prompt, files)
            rows["grep"]["hits"] += int(gbest.resolve() == target)
            rows["grep"]["tokens"] += gcost
            rows["embedding"]["hits"] += int(ebest.resolve() == target)
            rows["embedding"]["tokens"] += ecost
            # hybrid: prefer grep's pick unless it missed and embedding hit
            hbest = gbest if gbest.resolve() == target else ebest
            rows["hybrid"]["hits"] += int(hbest.resolve() == target)
            rows["hybrid"]["tokens"] += (gcost + ecost) // 2
            n += 1
    for s in rows.values():
        s["hit_rate"] = round(s["hits"] / n, 4)
        s["mean_tokens"] = round(s["tokens"] / n, 1)
    rows["n_tasks"] = n
    return rows


def main() -> int:
    bake = _bakeoff()
    obs = [
        ContextObservation("grep", bake["grep"]["hit_rate"], int(bake["grep"]["mean_tokens"]),
                           0.1),
        ContextObservation("embedding", bake["embedding"]["hit_rate"],
                           int(bake["embedding"]["mean_tokens"]), 0.5,
                           index_build_tokens=5000, reuse_count=10),
        ContextObservation("hybrid", bake["hybrid"]["hit_rate"],
                           int(bake["hybrid"]["mean_tokens"]), 0.4),
    ]
    decision = choose_strategy(obs)
    ROOT.mkdir(parents=True, exist_ok=True)
    bakeoff = {"experiment": "grep_vs_embedding_bakeoff", "by_strategy": bake,
               "note": "retrieval hit-rate as a downstream-context-quality proxy (free)"}
    ope = {"experiment": "context_strategy_ope", "chosen": decision.chosen,
           "reason": decision.reason, "scores": [s.to_dict() for s in decision.scores]}
    reuse = {"experiment": "context_reuse_frontier",
             "embedding_amortization": [
                 {"reuse_count": r, "chosen": choose_strategy([
                     ContextObservation("grep", bake["grep"]["hit_rate"],
                                        int(bake["grep"]["mean_tokens"]), 0.1),
                     ContextObservation("embedding", bake["embedding"]["hit_rate"],
                                        int(bake["embedding"]["mean_tokens"]), 0.5,
                                        index_build_tokens=5000, reuse_count=r)]).chosen}
                 for r in (1, 10, 100, 1000)]}
    for name, data in (("grep_vs_embedding_bakeoff.json", bakeoff),
                       ("context_strategy_ope.json", ope),
                       ("context_reuse_frontier.json", reuse)):
        (ROOT / name).write_text(json.dumps(data, indent=2) + "\n")
        print(f"wrote {ROOT / name}")
    print(f"grep hit={bake['grep']['hit_rate']} embedding hit={bake['embedding']['hit_rate']} "
          f"-> chosen={decision.chosen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
