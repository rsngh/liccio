"""Graph-ranked repo map (Aider-style) — research-backed context feature.

Asserts the core property from the repo-map research: the most widely-REFERENCED definitions
rank highest, the map is deterministic and budget-bounded, and the compiler exposes it as the
`repo_map` strategy.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from acp.context.compiler import ContextCompiler
from acp.context.repo_map import build_repo_map
from acp.schemas.task import Task

# core.py defines a widely-used API; three files reference it; one symbol is never referenced.
_FILES = {
    "core.py": ("def central_api(x):\n    return x + 1\n\n"
                "class Helper:\n    def aux(self):\n        return 0\n"),
    "a.py": "from core import central_api\ndef a1():\n    return central_api(1)\n",
    "b.py": "from core import central_api\ndef b1():\n    return central_api(2)\n",
    "c.py": ("from core import central_api, Helper\n"
             "def c1():\n    return central_api(3) + Helper().aux()\n"),
    "lonely.py": "def never_used():\n    return 42\n",
}


def test_referenced_symbols_rank_higher() -> None:
    m = build_repo_map(_FILES, token_budget=1024)
    rank = {s.name: s.rank for s in m.symbols}
    assert rank["central_api"] == max(rank.values())  # referenced by 3 files -> most central
    assert rank["central_api"] > rank["a1"]            # leaf functions rank below the hub
    assert rank["central_api"] > rank.get("never_used", 0.0)
    # the hub's reference count is observed, not assumed
    refs = {s.name: s.references for s in m.symbols}
    assert refs["central_api"] >= 3


def test_repo_map_is_deterministic() -> None:
    assert build_repo_map(_FILES, token_budget=1024).text == \
        build_repo_map(_FILES, token_budget=1024).text


def test_repo_map_respects_budget() -> None:
    big = {f"f{i}.py": f"def func_{i}(a, b, c):\n    return a + b + c\n" for i in range(200)}
    m = build_repo_map(big, token_budget=128)
    assert m.token_estimate <= 128
    assert m.symbols  # still produces a non-empty map within the small budget


def test_repo_map_signatures_not_bodies() -> None:
    m = build_repo_map(_FILES, token_budget=1024)
    assert "central_api" in m.text
    assert "def central_api(x):" in m.text
    assert "return x + 1" not in m.text  # body is omitted; only the signature is mapped


def test_empty_repo_map() -> None:
    m = build_repo_map({"readme.txt": "no code here"}, token_budget=512)
    assert m.text == "" and m.symbols == []


def test_repo_map_covers_more_apis_per_token_than_chunk_retrieval() -> None:
    """The research claim, measured: at a fixed (tight) token budget the signature map exposes
    far more of the repo's APIs than full-body chunk retrieval — breadth from everywhere."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        names = []
        for i in range(30):
            nm = f"service_{i}_handler"
            names.append(nm)
            body = "\n".join(f"    step_{j} = {j} * {i}" for j in range(12))
            (root / f"svc_{i}.py").write_text(f"def {nm}(payload):\n{body}\n    return payload\n")
        task = Task(repo_id="r", title="wire the services", body="connect the service handlers")

        def coverage(strategy: str) -> int:
            pack = ContextCompiler(str(root), "r", "s").compile(
                task, strategy=strategy, token_budget=400)
            txt = "\n".join(it.content for it in pack.items)
            return sum(1 for n in names if f"def {n}" in txt)

        repo_map_cov = coverage("repo_map")
        hybrid_cov = coverage("hybrid_keyword_embedding")
    assert repo_map_cov >= 3 * max(hybrid_cov, 1), (repo_map_cov, hybrid_cov)
    assert repo_map_cov >= 15  # covers the majority of APIs within the tight budget


def test_compiler_repo_map_strategy_emits_map_chunk() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for path, src in _FILES.items():
            (root / path).write_text(src)
        pack = ContextCompiler(str(root), "r", "s").compile(
            Task(repo_id="r", title="call the central api", body="use central_api"),
            strategy="repo_map", token_budget=4000)
    map_chunks = [i for i in pack.items if i.kind == "repo_map_chunk"]
    assert len(map_chunks) == 1
    assert "central_api" in map_chunks[0].content
    assert pack.strategy == "repo_map"
