"""MetaRouter Arena — deterministic substrate tests (GOALS Alpha 42 P0).

No API keys: exercises the scoring math (verified success uses CONCLUSIVE attempts as the
denominator; availability is separated from capability) and the deterministic floor/oracle
policies + the held-out hidden-test verifier.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from evals.metarouter_arena.policies import policy_cheap_static, policy_oracle, verify
from evals.metarouter_arena.schema import AdapterStatus, ArenaAttempt, PolicyScore
from evals.metarouter_arena.task_pack import TASK_PACK


def test_verified_rate_uses_conclusive_denominator_not_availability() -> None:
    s = PolicyScore(policy="p")
    # 1 solved+conclusive, 1 conclusive-but-failed, 1 unavailable (must not count against rate)
    s.add(ArenaAttempt("t1", "p", AdapterStatus.LIVE_CONCLUSIVE.value, solved=True,
                       public_solved=True, conclusive=True, cost_usd=0.01, latency_s=1.0))
    s.add(ArenaAttempt("t2", "p", AdapterStatus.LIVE_CONCLUSIVE.value, solved=False,
                       public_solved=False, conclusive=True, cost_usd=0.01, latency_s=1.0))
    s.add(ArenaAttempt("t3", "p", AdapterStatus.UNAVAILABLE.value, solved=False,
                       public_solved=False, conclusive=False, cost_usd=0.0, latency_s=0.0))
    d = s.to_dict()
    assert d["verified_success_rate"] == 0.5          # 1 solved / 2 conclusive (not /3)
    assert d["adapter_unavailable_rate"] == round(1 / 3, 4)
    assert d["conclusive_rate"] == round(2 / 3, 4)
    assert d["cost_per_verified_success"] == 0.02     # total cost / verified successes


def test_cost_per_verified_success_none_when_no_success() -> None:
    s = PolicyScore(policy="p")
    s.add(ArenaAttempt("t", "p", AdapterStatus.LIVE_CONCLUSIVE.value, solved=False,
                       public_solved=False, conclusive=True, cost_usd=0.05, latency_s=1.0))
    assert s.to_dict()["cost_per_verified_success"] is None


def test_oracle_solves_and_static_floor_fails_each_task() -> None:
    # offline fairness of the pack: reference fix passes the hidden test, no-op does not.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for spec in TASK_PACK:
            oracle = policy_oracle(spec, root)
            static = policy_cheap_static(spec, root)
            assert oracle.solved, f"{spec.name}: oracle (reference fix) must solve hidden test"
            assert oracle.conclusive and static.conclusive
            assert not static.solved, f"{spec.name}: no-op floor must not solve"


def test_hidden_test_verifier_independent_of_public() -> None:
    # a fix that satisfies only the public test must not be credited as verified (hidden) success
    spec = next(s for s in TASK_PACK if s.name == "stats_two_bug")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        from evals.metarouter_arena.policies import build_workspace
        ws = build_workspace(spec, root / "x")
        # public-only "fix": correct mean (public passes) but leave median buggy (hidden fails)
        (ws / spec.module_path).write_text(
            "def mean(xs):\n    return sum(xs) / len(xs)\n\n"
            "def median(xs):\n    return xs[len(xs) // 2]\n")
        solved, public = verify(ws, spec, root / "x")
        assert public and not solved
