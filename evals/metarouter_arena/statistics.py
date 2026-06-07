"""Arena statistics — Wilson confidence intervals (GOALS Alpha 43 P0).

Verified-success rates need intervals, not point estimates, before any promotion claim. Pure
Python (no scipy): Wilson score interval, robust at small n.
"""

from __future__ import annotations

import math


def wilson_ci(successes: int, n: int, *, z: float = 1.96) -> tuple[float, float, float]:
    """Return (point, lo, hi) for a binomial proportion at confidence ~95% (z=1.96)."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(p, 4), round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))


def beats_with_confidence(succ_a: int, n_a: int, succ_b: int, n_b: int) -> bool:
    """True iff A's Wilson lower bound exceeds B's Wilson upper bound (A reliably beats B)."""
    _, lo_a, _ = wilson_ci(succ_a, n_a)
    _, _, hi_b = wilson_ci(succ_b, n_b)
    return lo_a > hi_b
