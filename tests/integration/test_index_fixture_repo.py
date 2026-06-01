"""Context indexing + compilation tests against the bugfix fixture (charter §10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from acp.context.compiler import ContextCompiler
from acp.context.indexer import RepoIndexer
from acp.context.token_budget import ContextBudgeter
from acp.schemas.task import Task

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/repos/python_buggy_app"


@pytest.fixture
def bug_task() -> Task:
    return Task(
        repo_id="repo_1",
        title="Fix divide by zero in calculator",
        body="divide() returns 0 on zero divisor; it should raise ZeroDivisionError.",
        acceptance_criteria=["divide(x, 0) raises ZeroDivisionError", "tests updated"],
        labels=["bug", "calculator"],
    )


def test_index_collects_chunks_and_languages() -> None:
    idx = RepoIndexer(FIXTURE, "repo_1", "snap_1").index()
    assert idx.language_summary.get("python", 0) >= 1
    kinds = {c.kind for c in idx.chunks}
    assert "instruction_chunk" in kinds  # AGENTS.md
    assert "manifest_chunk" in kinds  # pyproject.toml
    assert any(c.kind == "test_chunk" for c in idx.chunks)
    assert any(c.symbol_name == "divide" for c in idx.chunks)


def test_no_secret_files_indexed(tmp_path) -> None:
    (tmp_path / ".env").write_text("SECRET=abc")
    (tmp_path / "app.py").write_text("x = 1\n")
    idx = RepoIndexer(tmp_path, "r", "s").index()
    assert all(".env" not in c.path for c in idx.chunks)


def test_compile_retrieves_relevant_files(bug_task: Task) -> None:
    pack = ContextCompiler(FIXTURE, "repo_1", "snap_1").compile(bug_task, token_budget=80_000)
    paths = {it.path for it in pack.items}
    assert any("calculator.py" in p for p in paths)
    assert any("test_calculator.py" in p for p in paths)
    # AGENTS.md instructions included
    assert any(it.kind == "instruction_chunk" and "AGENTS" in it.path for it in pack.items)
    # task spec included
    assert any(it.path == "__task_spec__" for it in pack.items)
    assert pack.retrieval_trace is not None
    assert pack.retrieval_trace.decisions


def test_budget_never_exceeded(bug_task: Task) -> None:
    pack = ContextCompiler(FIXTURE, "repo_1", "snap_1").compile(bug_task, token_budget=120)
    assert pack.token_estimate <= 120 + max(
        (it.token_estimate for it in pack.items if it.path == "__task_spec__"), default=0
    )
    # required items may exceed by their own size, but candidate budget respected
    assert pack.token_estimate <= 80_000


def test_context_pack_hash_deterministic(bug_task: Task) -> None:
    c = ContextCompiler(FIXTURE, "repo_1", "snap_1")
    p1 = c.compile(bug_task, token_budget=80_000)
    p2 = c.compile(bug_task, token_budget=80_000)
    assert p1.content_hash == p2.content_hash


def test_budgeter_dedupes_and_caps() -> None:
    from acp.context.chunks import make_chunk

    items = [
        make_chunk(kind="file_chunk", path="a.py", content="dup content here"),
        make_chunk(kind="file_chunk", path="a.py", content="dup content here"),  # duplicate
        make_chunk(kind="file_chunk", path="b.py", content="other content"),
    ]
    res = ContextBudgeter(token_budget=10_000).select(items)
    assert len(res.selected) == 2  # duplicate removed
    assert any(d["reason"] == "duplicate" for d in res.decisions)
