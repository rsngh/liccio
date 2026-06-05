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


@dataclass
class BayesianCanaryResult:
    control_rate: float
    canary_rate: float
    prob_canary_better: float       # P(p_canary > p_control) under Beta-Binomial
    control_ci: tuple[float, float]  # 95% credible interval
    canary_ci: tuple[float, float]
    control_n: int
    canary_n: int
    contaminated: bool
    promote: bool
    reasons: list[str]


def _beta_moments(successes: int, n: int) -> tuple[float, float]:
    """Mean + variance of a Beta(1+s, 1+f) posterior (uniform prior)."""
    a, b = 1.0 + successes, 1.0 + (n - successes)
    mean = a / (a + b)
    var = (a * b) / ((a + b) ** 2 * (a + b + 1))
    return mean, var


def _ci(successes: int, n: int) -> tuple[float, float]:
    mean, var = _beta_moments(successes, n)
    sd = math.sqrt(var)
    return (round(max(0.0, mean - 1.96 * sd), 4), round(min(1.0, mean + 1.96 * sd), 4))


def bayesian_canary(
    control_cells: list[Any], canary_cells: list[Any], *,
    prob_threshold: float = 0.95, min_lift: float = 0.0, min_per_arm: int = 5,
) -> BayesianCanaryResult:
    """Beta-binomial canary (WS14): P(canary solve-rate > control) via a normal
    approximation to each Beta posterior. Promotes only when that probability clears
    ``prob_threshold`` with adequate, uncontaminated conclusive samples."""
    ch = build_hygiene_report(control_cells)
    kh = build_hygiene_report(canary_cells)
    c_n, c_s = ch.n_conclusive, ch.n_success
    k_n, k_s = kh.n_conclusive, kh.n_success
    cm, cv = _beta_moments(c_s, c_n) if c_n else (0.0, 0.0)
    km, kv = _beta_moments(k_s, k_n) if k_n else (0.0, 0.0)
    # P(canary > control): difference of two ~Normal posteriors.
    sd = math.sqrt(cv + kv)
    prob = round(_norm_cdf((km - cm) / sd), 4) if sd > 0 else (1.0 if km > cm else 0.0)
    reasons: list[str] = []
    contaminated = ch.contaminated or kh.contaminated
    if contaminated:
        reasons.append("an arm's measurement is contaminated")
    if c_n < min_per_arm or k_n < min_per_arm:
        reasons.append(f"low N (control={c_n}, canary={k_n}) -> abstain")
    if (km - cm) < min_lift:
        reasons.append(f"lift {round(km - cm, 4)} < min_lift {min_lift}")
    if prob < prob_threshold:
        reasons.append(f"P(canary>control)={prob} < {prob_threshold}")
    return BayesianCanaryResult(
        control_rate=round(cm, 4), canary_rate=round(km, 4), prob_canary_better=prob,
        control_ci=_ci(c_s, c_n) if c_n else (0.0, 0.0),
        canary_ci=_ci(k_s, k_n) if k_n else (0.0, 0.0),
        control_n=c_n, canary_n=k_n, contaminated=contaminated,
        promote=not reasons, reasons=reasons)
