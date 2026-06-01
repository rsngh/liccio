"""Retriever stress (charter §21.7): synthetic large repo, budget never exceeded."""

from __future__ import annotations

import time

import pytest

from acp.context.compiler import ContextCompiler
from acp.schemas.task import Task


@pytest.fixture
def big_repo(tmp_path):
    for i in range(400):
        d = tmp_path / f"pkg{i % 20}"
        d.mkdir(exist_ok=True)
        (d / f"mod{i}.py").write_text(
            f"def func_{i}(x):\n    return x + {i}\n\n\nclass C{i}:\n    value = {i}\n"
        )
    # a binary file + a secret file that must be excluded
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    (tmp_path / ".env").write_text("SECRET=should-not-be-indexed")
    return tmp_path


@pytest.mark.slow
def test_index_and_budget_respected(big_repo) -> None:
    task = Task(repo_id="r", title="modify func_42", body="change func_42 behavior")
    t0 = time.monotonic()
    pack = ContextCompiler(big_repo, "r", "s").compile(task, token_budget=5000)
    elapsed = time.monotonic() - t0

    # budget respected for non-required items
    non_required = sum(it.token_estimate for it in pack.items if it.path != "__task_spec__")
    assert non_required <= 5000
    # no secrets / binaries leaked
    assert all(".env" not in it.path for it in pack.items)
    assert all("blob.bin" not in it.path for it in pack.items)
    assert pack.retrieval_trace is not None
    print(f"indexed+compiled big repo in {elapsed:.2f}s, {len(pack.items)} items")


@pytest.mark.slow
def test_deterministic_under_stress(big_repo) -> None:
    task = Task(repo_id="r", title="modify func_7", body="tweak func_7")
    c = ContextCompiler(big_repo, "r", "s")
    assert c.compile(task, token_budget=4000).content_hash == \
        c.compile(task, token_budget=4000).content_hash
