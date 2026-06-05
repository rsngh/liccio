"""DeepConf-style confidence-based pruning (Alpha 24 area 14).

DeepConf uses intrinsic confidence to prune weak reasoning paths, reporting large token
savings while matching or improving accuracy. For an orchestrator the same idea cuts cost
in three places: (a) prune low-confidence candidate patches BEFORE running their (expensive)
execution verification; (b) confidence-weighted voting to pick among candidates; (c) early
stop sampling once a high-confidence candidate appears.

Safety: high-risk/security tasks are pruned conservatively (a higher floor on kept
candidates and a higher early-stop bar) so confidence pruning can never skip verification on
work that must be checked. The pruner never drops below ``min_keep`` candidates.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class ScoredCandidate:
    index: int
    confidence: float                # 0..1 intrinsic confidence
    answer_key: str | None = None    # e.g. a content hash, for agreement-weighted voting


@dataclass
class PruneResult:
    kept: list = field(default_factory=list)        # indices kept for verification
    pruned: list = field(default_factory=list)      # indices pruned (skip verification)
    keep_fraction: float = 1.0
    estimated_verify_savings: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _risk_floor(min_keep: int, risk: str) -> int:
    # never prune aggressively on high-risk: keep at least 3 (or all if fewer).
    return max(min_keep, 3) if risk == "high" else min_keep


def prune_by_confidence(cands: list[ScoredCandidate], *, threshold: float = 0.5,
                        min_keep: int = 1, risk: str = "low",
                        cost_per_verify: float = 0.0) -> PruneResult:
    """Keep candidates with confidence >= threshold, but never fewer than the risk floor.

    Returns the kept/pruned index split plus the estimated verification cost saved by not
    running the pruned candidates' execution checks.
    """
    if not cands:
        return PruneResult(rationale="no candidates")
    floor = min(_risk_floor(min_keep, risk), len(cands))
    ranked = sorted(cands, key=lambda c: (-c.confidence, c.index))
    kept = [c for c in ranked if c.confidence >= threshold]
    if len(kept) < floor:                       # top up to the floor by confidence
        kept = ranked[:floor]
    kept_idx = sorted(c.index for c in kept)
    pruned_idx = sorted(c.index for c in cands if c.index not in set(kept_idx))
    savings = round(len(pruned_idx) * cost_per_verify, 6)
    return PruneResult(
        kept=kept_idx, pruned=pruned_idx,
        keep_fraction=round(len(kept_idx) / len(cands), 4),
        estimated_verify_savings=savings,
        rationale=(f"kept {len(kept_idx)}/{len(cands)} at conf>={threshold} "
                   f"(risk={risk}, floor={floor})"))


def confidence_weighted_vote(cands: list[ScoredCandidate]) -> str | None:
    """Pick the answer_key with the highest summed confidence (DeepConf-style voting)."""
    weights: dict[str, float] = defaultdict(float)
    for c in cands:
        if c.answer_key is not None:
            weights[c.answer_key] += c.confidence
    if not weights:
        return None
    return max(weights.items(), key=lambda kv: (kv[1], kv[0]))[0]


def should_early_stop(cands: list[ScoredCandidate], *, high_conf_threshold: float = 0.9,
                      risk: str = "low") -> bool:
    """Stop sampling once a candidate is confident enough — stricter bar on high risk."""
    bar = max(high_conf_threshold, 0.97) if risk == "high" else high_conf_threshold
    return any(c.confidence >= bar for c in cands)
