"""Offline policy evaluation (Alpha 6, WS3).

Estimate the value of a *target* routing policy from a log collected under a
*behavior* policy — without re-running any agent. This is what lets ACP answer
"if we deploy the supervised meta-router instead of the bandit, what reward/cost
should we expect?" before paying to find out.

Estimators
----------
* **IPS**  — inverse-propensity scoring; unbiased but high-variance.
* **SNIPS** — self-normalized IPS; biased but far lower variance.
* **clipped IPS** — weights capped to bound variance (reports the clipped mass).
* **DR**   — doubly-robust: a fitted reward model baseline + IPS correction on
  the residual. Consistent if *either* the propensities or the reward model are
  right.

Every estimate carries a **bootstrap confidence interval** and the run reports
**diagnostics** (effective sample size, weight tail, propensity overlap) so a
reviewer can tell whether the estimate is trustworthy or the log lacks overlap.

The richer dataclass API (:class:`OPESample` + :class:`TargetPolicy`) is the one
to use for new work; :func:`from_decision_log` adapts the existing
``(PolicyDecision, RewardEvent)`` logs the service already persists.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from acp.routing.policy import PolicyDecision
from acp.schemas.learning import RewardEvent


class OPEError(ValueError):
    pass


@dataclass
class OPESample:
    """One logged decision: chosen action, its propensity, the realized reward,
    and the action set that was available (needed for the target's expectation)."""

    context_key: str
    action_key: str
    behavior_prob: float
    reward: float
    candidates: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (0.0 < self.behavior_prob <= 1.0):
            raise OPEError(f"invalid behavior propensity: {self.behavior_prob}")
        if self.action_key not in (self.candidates or [self.action_key]):
            # The logged action must be a member of its own candidate set.
            self.candidates = [*self.candidates, self.action_key]


# A target policy returns pi_target(action | context, candidates).
TargetPolicy = Callable[[str, str, list[str]], float]


@dataclass
class Estimate:
    value: float
    ci_low: float
    ci_high: float

    def as_dict(self) -> dict:
        return {"value": round(self.value, 6),
                "ci_low": round(self.ci_low, 6),
                "ci_high": round(self.ci_high, 6)}


@dataclass
class Diagnostics:
    n: int
    effective_sample_size: float
    max_weight: float
    mean_weight: float
    min_behavior_prob: float
    overlap: float  # fraction of samples the target would ever take (pi_t > 0)
    clip_fraction: float  # fraction of weight mass removed by clipping

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "effective_sample_size": round(self.effective_sample_size, 3),
            "max_weight": round(self.max_weight, 4),
            "mean_weight": round(self.mean_weight, 4),
            "min_behavior_prob": round(self.min_behavior_prob, 6),
            "overlap": round(self.overlap, 4),
            "clip_fraction": round(self.clip_fraction, 4),
        }


@dataclass
class OPEReport:
    ips: Estimate
    snips: Estimate
    clipped_ips: Estimate
    dr: Estimate
    diagnostics: Diagnostics
    weight_clip: float
    n: int

    def as_dict(self) -> dict:
        return {
            "ips": self.ips.as_dict(),
            "snips": self.snips.as_dict(),
            "clipped_ips": self.clipped_ips.as_dict(),
            "dr": self.dr.as_dict(),
            "diagnostics": self.diagnostics.as_dict(),
            "weight_clip": self.weight_clip,
            "n": self.n,
        }

    def best_estimate(self) -> float:
        """The estimate to trust by default: DR (consistent under either model)."""
        return self.dr.value


def fit_reward_model(samples: list[OPESample]) -> Callable[[str, str], float]:
    """Per-(context, action) mean reward with context- and global-mean fallback.

    This is the q-hat baseline for the doubly-robust estimator. It is deliberately
    simple and non-parametric so DR stays well-defined on small logs.
    """
    by_ctx_action: dict[tuple[str, str], list[float]] = {}
    by_ctx: dict[str, list[float]] = {}
    all_r: list[float] = []
    for s in samples:
        by_ctx_action.setdefault((s.context_key, s.action_key), []).append(s.reward)
        by_ctx.setdefault(s.context_key, []).append(s.reward)
        all_r.append(s.reward)
    global_mean = sum(all_r) / len(all_r) if all_r else 0.0

    def q(ctx: str, action: str) -> float:
        key = (ctx, action)
        if key in by_ctx_action:
            vs = by_ctx_action[key]
            return sum(vs) / len(vs)
        if ctx in by_ctx:
            vs = by_ctx[ctx]
            return sum(vs) / len(vs)
        return global_mean

    return q


def _weights(samples: list[OPESample], target: TargetPolicy) -> list[float]:
    out = []
    for s in samples:
        tp = target(s.context_key, s.action_key, s.candidates)
        out.append(max(0.0, tp) / s.behavior_prob)
    return out


def _ips(samples, weights) -> float:
    return sum(w * s.reward for w, s in zip(weights, samples, strict=True)) / len(samples)


def _snips(samples, weights) -> float:
    wsum = sum(weights)
    if wsum <= 0:
        return 0.0
    return sum(w * s.reward for w, s in zip(weights, samples, strict=True)) / wsum


def _dr(samples, weights, target, q) -> float:
    total = 0.0
    for w, s in zip(weights, samples, strict=True):
        # Direct expectation under the target over the candidate set.
        direct = sum(target(s.context_key, a, s.candidates) * q(s.context_key, a)
                     for a in s.candidates)
        total += direct + w * (s.reward - q(s.context_key, s.action_key))
    return total / len(samples)


def _diagnostics(samples, weights, target, clip) -> Diagnostics:
    n = len(samples)
    wsum = sum(weights)
    wsq = sum(w * w for w in weights)
    ess = (wsum * wsum / wsq) if wsq > 0 else 0.0
    clipped = [min(w, clip) for w in weights]
    clip_fraction = (wsum - sum(clipped)) / wsum if wsum > 0 else 0.0
    overlap = sum(
        1 for s in samples if target(s.context_key, s.action_key, s.candidates) > 0
    ) / n
    return Diagnostics(
        n=n,
        effective_sample_size=ess,
        max_weight=max(weights) if weights else 0.0,
        mean_weight=wsum / n if n else 0.0,
        min_behavior_prob=min(s.behavior_prob for s in samples),
        overlap=overlap,
        clip_fraction=clip_fraction,
    )


def _bootstrap_ci(
    samples: list[OPESample], target: TargetPolicy, q, estimator: str,
    clip: float, *, n_boot: int, seed: int, alpha: float,
) -> tuple[float, float]:
    """Percentile bootstrap CI by resampling decisions with replacement."""
    if len(samples) < 2 or n_boot <= 0:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(samples)
    vals: list[float] = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        boot = [samples[i] for i in idx]
        w = _weights(boot, target)
        if estimator == "ips":
            vals.append(_ips(boot, w))
        elif estimator == "snips":
            vals.append(_snips(boot, w))
        elif estimator == "clipped_ips":
            vals.append(_ips(boot, [min(x, clip) for x in w]))
        elif estimator == "dr":
            vals.append(_dr(boot, w, target, q))
    vals.sort()
    lo = vals[int((alpha / 2) * len(vals))]
    hi = vals[min(len(vals) - 1, int((1 - alpha / 2) * len(vals)))]
    return (lo, hi)


def evaluate_policy(
    samples: list[OPESample],
    target: TargetPolicy,
    *,
    reward_model: Callable[[str, str], float] | None = None,
    weight_clip: float = 20.0,
    n_boot: int = 200,
    seed: int = 1234,
    alpha: float = 0.05,
) -> OPEReport:
    """Full OPE report: IPS / SNIPS / clipped-IPS / DR + bootstrap CIs + diagnostics."""
    if not samples:
        raise OPEError("empty log")
    q = reward_model or fit_reward_model(samples)
    weights = _weights(samples, target)
    clipped = [min(w, weight_clip) for w in weights]

    def est(estimator: str, point: float) -> Estimate:
        lo, hi = _bootstrap_ci(samples, target, q, estimator, weight_clip,
                               n_boot=n_boot, seed=seed, alpha=alpha)
        return Estimate(value=point, ci_low=lo, ci_high=hi)

    return OPEReport(
        ips=est("ips", _ips(samples, weights)),
        snips=est("snips", _snips(samples, weights)),
        clipped_ips=est("clipped_ips", _ips(samples, clipped)),
        dr=est("dr", _dr(samples, weights, target, q)),
        diagnostics=_diagnostics(samples, weights, target, weight_clip),
        weight_clip=weight_clip,
        n=len(samples),
    )


def from_decision_log(
    log: list[tuple[PolicyDecision, RewardEvent]],
) -> list[OPESample]:
    """Adapt persisted ``(PolicyDecision, RewardEvent)`` pairs into OPE samples.

    Candidate keys are taken from ``decision.candidate_scores`` when present,
    falling back to the single logged action.
    """
    samples: list[OPESample] = []
    for decision, reward in log:
        cands = list(decision.candidate_scores.keys()) or [decision.action.key()]
        samples.append(OPESample(
            context_key=decision.context_key,
            action_key=decision.action.key(),
            behavior_prob=decision.action_probability,
            reward=reward.reward,
            candidates=cands,
        ))
    return samples
