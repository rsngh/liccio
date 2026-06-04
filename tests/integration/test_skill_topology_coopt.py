"""Topology + skill co-optimization (Alpha 21 WS15)."""

from __future__ import annotations

from acp.training.skill_topology_coopt import CoOptArm, cooptimize


def test_skip_reviewer_with_strong_skill_chosen_when_cheaper() -> None:
    arms = [
        CoOptArm([], "skill_full", success_rate=1.0, cost=0.020, sample_size=5),
        CoOptArm(["skip_reviewer"], "skill_verify", success_rate=1.0, cost=0.008,
                 sample_size=5),
    ]
    choice = cooptimize(arms, "bugfix", "low")
    assert choice.topology == ["skip_reviewer"] and choice.skill_id == "skill_verify"
    assert choice.cost_saving == 0.012


def test_skip_that_degrades_success_not_chosen() -> None:
    arms = [
        CoOptArm([], "s", success_rate=1.0, cost=0.020, sample_size=5),
        CoOptArm(["skip_reviewer"], "s", success_rate=0.7, cost=0.008, sample_size=5),
    ]
    choice = cooptimize(arms, "bugfix", "low")
    assert choice.topology == []


def test_security_never_co_opts_unsafe_skip() -> None:
    arms = [
        CoOptArm([], "s", success_rate=1.0, cost=0.030, sample_size=5),
        CoOptArm(["skip_strict_verification"], "s", success_rate=1.0, cost=0.005,
                 sample_size=5),
    ]
    choice = cooptimize(arms, "security_fix", "high")
    assert choice.topology == []  # safety overrides the cheaper unsafe arm
