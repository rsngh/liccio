# ruff: noqa: E501
"""Aging-aware memory revision (AgingBench 2605.26302; Learning to Forget 2603.14517).

Today's `ExperienceBank.avoid_strategies` is "ever failed" — sticky: once a strategy fails a
signature it is avoided forever, so after the repo evolves *back* (or the failure was transient) the
strategy can never be re-used (revision aging). And decay is never applied, so old episodes never
age out (no forgetting). This module adds:

  * `consolidate` — sleep-style dedup: collapse repeated (signature, strategy) episodes into their
    net recency-weighted signal, so memory doesn't bloat and interfere as it grows;
  * recency/aging-aware `recommend_by_recency` / `avoid_by_recency` — decide from the *net decayed
    reward* (recent outcomes dominate), so a strategy can be re-used once old failures age out;
  * `recommend_recipe` — procedural memory: return the whole winning lever *sequence* (Memp /
    Remember-Me-Refine-Me), not just one strategy, so recall seeds the entire cheap path.

Deterministic, dependency-free. Designed to plug into `route_and_solve(recommend_fn=, avoid_fn=)`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from acp.memory.experience_bank import ExperienceBank, ExperienceEpisode


def net_strategy_scores(bank: ExperienceBank, *, tenant: str, failure_signature: str) -> dict[str, float]:
    """Per-strategy NET decayed reward for a signature (positive minus negative, recency-weighted)."""
    scores: dict[str, float] = defaultdict(float)
    for ep in bank.read(tenant=tenant, failure_signature=failure_signature):
        scores[ep.context_strategy] += ep.reward * ep.decay_score
    return dict(scores)


def recommend_by_recency(bank: ExperienceBank, *, tenant: str, failure_signature: str) -> str | None:
    """Best strategy by NET decayed reward (must be positive) — re-usable after old failures age out."""
    scores = net_strategy_scores(bank, tenant=tenant, failure_signature=failure_signature)
    best = max(scores.items(), key=lambda kv: kv[1], default=(None, 0.0))
    return best[0] if best[1] > 0 else None


def avoid_by_recency(bank: ExperienceBank, *, tenant: str, failure_signature: str) -> set[str]:
    """Avoid only strategies whose CURRENT net decayed reward is negative (not 'ever failed')."""
    return {s for s, v in net_strategy_scores(bank, tenant=tenant,
                                              failure_signature=failure_signature).items() if v < 0}


def consolidate(bank: ExperienceBank) -> int:
    """Sleep-style consolidation: collapse duplicate (scope, signature, strategy) episodes into one
    merged episode carrying the summed reward + latest timestamp. Returns episodes removed."""
    groups: dict[tuple, list[ExperienceEpisode]] = defaultdict(list)
    for ep in bank.episodes:
        if ep.quarantined:
            continue
        groups[(ep.privacy_scope, ep.failure_signature, ep.context_strategy)].append(ep)
    merged: list[ExperienceEpisode] = [ep for ep in bank.episodes if ep.quarantined]
    removed = 0
    for eps in groups.values():
        if len(eps) == 1:
            merged.append(eps[0])
            continue
        net = sum(e.reward * e.decay_score for e in eps)
        latest = max(eps, key=lambda e: e.created_at)
        merged.append(replace(latest, reward=round(net, 6), decay_score=1.0,
                              verifier_outcome="solved" if net >= 0 else "failed"))
        removed += len(eps) - 1
    bank.episodes = merged
    return removed


def recommend_recipe(bank: ExperienceBank, *, tenant: str, failure_signature: str) -> tuple[str, ...]:
    """Procedural memory: the winning lever SEQUENCE last recorded for this signature (or empty)."""
    pos = [ep for ep in bank.read(tenant=tenant, failure_signature=failure_signature,
                                  include_negative=False) if ep.recipe]
    return pos[0].recipe if pos else ()
