"""Statistical robustness for small-sample cells / uplift (Alpha 11+)."""

from __future__ import annotations

from acp.routing.cell_statistics import (
    min_n_for_resolution,
    robustly_better,
    two_proportion_significant,
    wilson_interval,
    wilson_lower_bound,
)


def test_wilson_is_robust_at_small_n() -> None:
    # 3/3 is NOT certainty: the normal approx gives [1,1]; Wilson keeps a wide interval.
    iv = wilson_interval(3, 3)
    assert iv.point == 1.0 and iv.low < 0.5 and iv.high == 1.0
    # a large sample tightens the interval
    big = wilson_interval(285, 300)
    assert big.high - big.low < 0.1 and big.low > 0.9


def test_lower_bound_orders_by_evidence_not_just_point() -> None:
    # a lucky 3/3 (point 1.0) must rank below a well-sampled 0.9 by lower bound
    assert wilson_lower_bound(3, 3) < wilson_lower_bound(270, 300)


def test_small_sample_difference_is_not_significant() -> None:
    # 2/2 vs 1/2 looks like a 0.5 gap but is not significant at n=2
    assert not two_proportion_significant(2, 2, 1, 2)
    # a real gap at large n is significant
    assert two_proportion_significant(95, 100, 70, 100)


def test_robustly_better_rejects_lucky_small_sample() -> None:
    # 3/3 (point 1.0) is NOT robustly better than a well-sampled 0.9
    assert not robustly_better(3, 3, 270, 300)
    # but a clearly-better, well-sampled arm is
    assert robustly_better(98, 100, 70, 100)


def test_min_n_for_resolution_grows_as_width_shrinks() -> None:
    assert min_n_for_resolution(0.8, 0.1) < min_n_for_resolution(0.8, 0.02)
    assert min_n_for_resolution(0.5, 0.05) > 50  # resolving a coin flip to +/-5% needs many


def test_zero_n_is_safe() -> None:
    assert wilson_interval(0, 0).low == 0.0
    assert not robustly_better(0, 0, 1, 1)
