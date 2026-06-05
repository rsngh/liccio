"""HeavySkill parallel-deliberation skill (Alpha 24 area 11)."""

from __future__ import annotations

from acp.agents.benchmark_suite import BENCH_TASKS
from acp.agents.weak_model_candidates import CandidatePatch, cost_usd
from acp.training.heavy_skill import HeavySkillPolicy, heavy_skill_solve, should_engage

EASY = next(t for t in BENCH_TASKS if t.difficulty == "easy")
HARD = next(t for t in BENCH_TASKS if t.difficulty == "hard")


def _stub(contents):
    def _s(task, i):
        return CandidatePatch(index=i, content=contents[i], in_tokens=100, out_tokens=50,
                              cost=cost_usd("gpt-4o-mini", 100, 50))
    return _s


def test_engagement_policy_skips_easy_low_risk() -> None:
    p = HeavySkillPolicy()
    assert not should_engage(p, difficulty="easy", risk="low")
    assert should_engage(p, difficulty="hard", risk="low")
    assert should_engage(p, difficulty="easy", risk="high")  # high-risk engages


def test_easy_task_runs_single_shot() -> None:
    res = heavy_skill_solve(EASY, sampler=_stub([EASY.fixed]), k=4, risk="low")
    assert not res.engaged and res.n_sampled == 1 and res.solved


def test_hard_task_engages_and_deliberates_to_a_passing_candidate() -> None:
    # 4 samples: 3 agree on the correct fix (high self-consistency), 1 buggy outlier.
    res = heavy_skill_solve(HARD, sampler=_stub([HARD.fixed, HARD.fixed, HARD.fixed,
                                                 HARD.buggy]), k=4, risk="low")
    assert res.engaged and res.n_sampled == 4 and res.solved
    assert res.best_index is not None


def test_pruning_reduces_verification_count() -> None:
    # one high-agreement correct cluster + low-agreement outliers get pruned pre-verify
    res = heavy_skill_solve(HARD, sampler=_stub([HARD.fixed, HARD.fixed, HARD.buggy,
                                                 HARD.fixed + "\n#x\n"]), k=4, risk="low")
    assert res.n_verified < res.n_sampled       # some candidates pruned before verification
    assert res.verify_savings_fraction > 0.0


def test_high_risk_keeps_more_candidates() -> None:
    res = heavy_skill_solve(HARD, sampler=_stub([HARD.fixed] + [HARD.buggy] * 3), k=4,
                            risk="high")
    assert res.engaged and res.n_verified >= 3  # conservative floor on high risk
