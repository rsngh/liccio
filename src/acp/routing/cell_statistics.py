"""Statistical robustness for small-sample capability cells / skill uplift (Alpha 11+).

The honest caveat on the capability matrix and SkillOpt uplift is small-sample fragility:
a cell with n=3 and a 100% solve rate is NOT the same evidence as n=200 at 95%, yet a raw
point estimate treats them alike. This module supplies the primitives to fix that:

- ``wilson_interval`` — a binomial confidence interval that stays sensible at small n
  (unlike the normal approximation, which gives [1.0, 1.0] for 3/3);
- ``wilson_lower_bound`` — the pessimistic estimate for conservative ("don't get fooled by a
  lucky small sample") ranking and promotion gates;
- ``two_proportion_significant`` — whether two solve rates differ beyond noise;
- ``robustly_better`` — A beats B only if A's lower bound exceeds B's point estimate AND the
  difference is significant; this is what a promotion gate should require, not a raw delta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z_95 = 1.959963984540054


@dataclass
class Interval:
    point: float
    low: float
    high: float

    def as_dict(self) -> dict:
        return {"point": round(self.point, 4), "low": round(self.low, 4),
                "high": round(self.high, 4)}


def wilson_interval(successes: int, n: int, z: float = Z_95) -> Interval:
    """Wilson score interval for a binomial proportion (robust at small n)."""
    if n <= 0:
        return Interval(0.0, 0.0, 1.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return Interval(point=p, low=max(0.0, center - margin), high=min(1.0, center + margin))


def wilson_lower_bound(successes: int, n: int, z: float = Z_95) -> float:
    """Conservative solve-rate estimate: the Wilson lower bound. Use for robust ranking."""
    return wilson_interval(successes, n, z).low


def two_proportion_significant(s1: int, n1: int, s2: int, n2: int, *,
                               alpha: float = 0.05) -> bool:
    """Two-sided two-proportion z-test: do the two solve rates differ significantly?"""
    if n1 == 0 or n2 == 0:
        return False
    p1, p2 = s1 / n1, s2 / n2
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return False
    zcrit = _z_for_alpha(alpha)
    return abs((p1 - p2) / se) >= zcrit


def _z_for_alpha(alpha: float) -> float:
    # two-sided critical z for common alphas; default to 95% if unmatched
    return {0.10: 1.6449, 0.05: 1.9600, 0.01: 2.5758}.get(round(alpha, 2), 1.9600)


def robustly_better(s_a: int, n_a: int, s_b: int, n_b: int, *, alpha: float = 0.05) -> bool:
    """A is robustly better than B: A's lower bound > B's point AND the gap is significant.

    This is the gate small samples need — a lucky 3/3 (lower bound ~0.44) does not clear a
    well-sampled 0.9, and a real difference must also survive a significance test.
    """
    if n_a == 0 or n_b == 0:
        return False
    pb = s_b / n_b
    return (wilson_lower_bound(s_a, n_a) > pb
            and two_proportion_significant(s_a, n_a, s_b, n_b, alpha=alpha))


def min_n_for_resolution(p: float = 0.8, half_width: float = 0.1, z: float = Z_95) -> int:
    """How many conclusive samples to resolve a proportion to +/- half_width (planning aid)."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    return max(1, math.ceil((z * z * p * (1 - p)) / (half_width * half_width)))
