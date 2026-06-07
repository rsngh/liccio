"""Heterogeneity arena — deterministic tests (no API keys).

Exercises the tier cost model, the escalation-ladder shapes, and the capability-gradient corpus
integrity (every reference fix solves its own hidden test; every buggy stub fails it). The live
solve-rate measurement is in reports/hetero_arena_*.json; here we only guard the substrate.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from evals.hetero_arena.policies import (
    ALL_POLICIES,
    CONTEXT_FIRST_LADDER,
    TIER_LADDER,
)
from evals.hetero_arena.tier_tasks import all_capability_tasks
from evals.hetero_arena.tiers import HAIKU, OPUS, SONNET, TIERS
from evals.metarouter_arena.policies import policy_cheap_static, policy_oracle


def test_tier_pricing_is_monotonic_and_correct() -> None:
    # same token counts -> haiku cheapest, opus dearest; opus output = 15x haiku, 5x sonnet
    a, b = 1000, 1000
    assert HAIKU.cost(a, b) < SONNET.cost(a, b) < OPUS.cost(a, b)
    assert round(OPUS.out_per_tok / HAIKU.out_per_tok, 1) == 15.0
    assert round(OPUS.out_per_tok / SONNET.out_per_tok, 1) == 5.0
    assert set(TIERS) == {"haiku", "sonnet", "opus"}


def test_ladders_are_well_formed() -> None:
    # tier ladder is pure model escalation at minimal context (isolates model strength)
    assert TIER_LADDER == (("haiku", "minimal"), ("sonnet", "minimal"), ("opus", "minimal"))
    # context-first ladder upgrades CONTEXT on the cheap model before paying for a bigger tier
    assert CONTEXT_FIRST_LADDER[0] == ("haiku", "minimal")
    assert CONTEXT_FIRST_LADDER[1] == ("haiku", "repo_map")  # cheaper fix tried before tier upgrade
    assert CONTEXT_FIRST_LADDER[-1][0] == "opus"             # opus is the last resort


def test_all_policies_registered() -> None:
    for name in ("haiku_single", "sonnet_single", "opus_single", "cost_aware_escalation",
                 "context_first_escalation", "best_of_k_haiku"):
        assert name in ALL_POLICIES


def test_capability_corpus_integrity() -> None:
    """Every task: reference fix passes its OWN held-out hidden test; buggy stub fails it."""
    tasks = all_capability_tasks()
    assert len(tasks) >= 20
    assert len({t.name for t in tasks}) == len(tasks)  # unique names
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for spec in tasks:
            assert spec.buggy != spec.fixed
            assert spec.public_test and spec.hidden_test
            o = policy_oracle(spec, root)
            f = policy_cheap_static(spec, root)
            assert o.solved and o.public_solved, f"oracle failed {spec.name}"
            assert not f.solved, f"buggy stub unexpectedly solved {spec.name}"


def test_difficulty_bands_span_easy_to_hard() -> None:
    bands = {t.difficulty_band for t in all_capability_tasks()}
    assert {"easy", "medium", "hard"} <= bands
