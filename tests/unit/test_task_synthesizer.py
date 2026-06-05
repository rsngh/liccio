"""Synthetic task-corpus generator + acceptance gate (Alpha 24 area 5)."""

from __future__ import annotations

from acp.agents.task_synthesizer import (
    accept_task,
    build_corpus,
    capability_gap_tasks,
    synthesize,
)


def test_synthesis_is_deterministic_from_seed() -> None:
    a = [t.name for t in synthesize(6, seed=7)]
    b = [t.name for t in synthesize(6, seed=7)]
    assert a == b and len(set(a)) == 6  # reproducible + unique names


def test_every_synthesized_task_passes_the_acceptance_gate() -> None:
    # The two-player guarantee: buggy fails, reference fix passes, no leakage.
    for task in synthesize(6, seed=3):
        ok, reason = accept_task(task)
        assert ok, f"{task.name} rejected: {reason}"


def test_corpus_covers_difficulty_bands() -> None:
    accepted, records = build_corpus(9, seed=1)
    assert len(accepted) == 9 and all(r["accepted"] for r in records)
    assert {t.difficulty for t in accepted} == {"easy", "medium", "hard"}


def test_leakage_is_rejected() -> None:
    from acp.agents.benchmark_suite import BenchTask
    leaky = BenchTask("x", "easy", "x.py", buggy="def f():\n    return 0\n",
                      fixed="def f():\n    return 1\n", test_src="from x import f\n",
                      prompt="fix it; the answer is def f():\n    return 1\n")
    ok, reason = accept_task(leaky)
    assert not ok and reason == "answer leakage"


def test_capability_gap_targets_sparse_cells() -> None:
    tasks = capability_gap_tasks([{"difficulty": "hard"}, {"difficulty": "medium"}], seed=5)
    assert {t.difficulty for t in tasks} == {"hard", "medium"}
