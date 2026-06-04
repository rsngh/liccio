"""Online A/B skill canary validation (Round 17).

Held-out validation gates a skill on a fixed batch; a canary validates it ONLINE: route
a fraction of live tasks with the candidate skill (canary) vs without (control) and
promote only on a statistically-significant conclusive-solve-rate lift. Both arms are
filtered to CONCLUSIVE attempts (the WS2 hard invariant), so infra noise can neither
inflate nor deflate the comparison. A contaminated arm blocks promotion outright.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from acp.evaluation.measurement_hygiene import build_hygiene_report


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass
class ABCanaryResult:
    control_n: int
    control_solved: int
    canary_n: int
    canary_solved: int
    control_rate: float
    canary_rate: float
    lift: float
    z_score: float
    p_value: float          # one-sided P(canary > control under H0)
    significant: bool
    contaminated: bool
    promote: bool
    reasons: list[str]


def evaluate_ab_canary(
    control_cells: list[Any], canary_cells: list[Any], *,
    alpha: float = 0.05, min_lift: float = 0.0, min_per_arm: int = 5,
) -> ABCanaryResult:
    """Two-proportion one-sided test of canary vs control conclusive solve rate.

    ``promote`` requires: both arms uncontaminated, each with >= ``min_per_arm``
    conclusive attempts, a lift >= ``min_lift``, and significance at ``alpha``.
    """
    ch = build_hygiene_report(control_cells)
    kh = build_hygiene_report(canary_cells)
    c_n, c_s = ch.n_conclusive, ch.n_success
    k_n, k_s = kh.n_conclusive, kh.n_success
    c_rate = (c_s / c_n) if c_n else 0.0
    k_rate = (k_s / k_n) if k_n else 0.0
    lift = round(k_rate - c_rate, 4)

    z = 0.0
    if c_n and k_n:
        pool = (c_s + k_s) / (c_n + k_n)
        se = math.sqrt(pool * (1 - pool) * (1 / c_n + 1 / k_n))
        z = (k_rate - c_rate) / se if se > 0 else 0.0
    p_value = round(1.0 - _norm_cdf(z), 4)
    significant = p_value < alpha

    reasons: list[str] = []
    contaminated = ch.contaminated or kh.contaminated
    if contaminated:
        reasons.append("an arm's measurement is contaminated")
    if c_n < min_per_arm or k_n < min_per_arm:
        reasons.append(f"insufficient conclusive samples (control={c_n}, canary={k_n})")
    if lift < min_lift:
        reasons.append(f"lift {lift} < min_lift {min_lift}")
    if not significant:
        reasons.append(f"not significant (p={p_value} >= alpha={alpha})")
    promote = not reasons
    return ABCanaryResult(
        control_n=c_n, control_solved=c_s, canary_n=k_n, canary_solved=k_s,
        control_rate=round(c_rate, 4), canary_rate=round(k_rate, 4), lift=lift,
        z_score=round(z, 4), p_value=p_value, significant=significant,
        contaminated=contaminated, promote=promote, reasons=reasons)
