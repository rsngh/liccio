"""HeavySkill: internalized parallel-deliberation skill (Alpha 24 area 11).

HeavySkill argues the reusable harness win is an inner skill: parallel reasoning followed by
deliberation. Here it is a cost-aware composition of pieces ACP already has: sample k
candidate patches (parallel reasoning), score each by SELF-CONSISTENCY (agreement among
samples is an intrinsic confidence signal), prune low-confidence ones with the DeepConf
pruner BEFORE the expensive execution verification, then deliberate — select the surviving
candidate that passes the held-out tests with the most minimal diff.

A cost-aware policy decides WHEN to engage: easy/low-risk tasks run single-shot (HeavySkill
is wasted there); harder or lower-confidence tasks engage the full parallel-deliberation
loop. This mirrors the empirical finding that parallel deliberation helps hard tasks most.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from acp.agents.benchmark_suite import BenchTask
from acp.agents.weak_model_candidates import Sampler, select_best, verify_candidate
from acp.orchestration.confidence_pruning import ScoredCandidate, prune_by_confidence


@dataclass
class HeavySkillPolicy:
    engage_difficulties: tuple = ("medium", "hard")
    engage_on_high_risk: bool = True
    prune_threshold: float = 0.34       # keep candidates with >= this agreement share
    min_keep: int = 1


def should_engage(policy: HeavySkillPolicy, *, difficulty: str, risk: str) -> bool:
    """Engage the heavy loop only where parallel deliberation is likely to pay off."""
    if policy.engage_on_high_risk and risk == "high":
        return True
    return difficulty in policy.engage_difficulties


def _self_consistency(patches) -> list[ScoredCandidate]:
    """Confidence = share of candidates that produced the same content (self-consistency)."""
    contents = [p.content for p in patches]
    counts = Counter(c for c in contents if c is not None)
    k = len(patches)
    out = []
    for p in patches:
        conf = (counts[p.content] / k) if p.content is not None else 0.0
        out.append(ScoredCandidate(index=p.index, confidence=conf, answer_key=p.content))
    return out


@dataclass
class HeavySkillResult:
    task_name: str
    engaged: bool
    n_sampled: int
    n_verified: int                     # candidates actually run through execution
    solved: bool
    best_index: int | None
    total_cost: float
    verify_savings_fraction: float      # share of candidates pruned before verification
    candidates: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["candidates"] = [dict(c.__dict__) for c in self.candidates]
        return d


def heavy_skill_solve(task: BenchTask, *, sampler: Sampler, k: int = 4,
                      risk: str = "low", policy: HeavySkillPolicy | None = None
                      ) -> HeavySkillResult:
    """Run the cost-aware parallel-deliberation loop (or a single shot if not engaged)."""
    p = policy or HeavySkillPolicy()
    engaged = should_engage(p, difficulty=task.difficulty, risk=risk)
    n = k if engaged else 1
    patches = [sampler(task, i) for i in range(n)]
    if engaged:
        scored = _self_consistency(patches)
        pruned = prune_by_confidence(scored, threshold=p.prune_threshold,
                                     min_keep=p.min_keep, risk=risk)
        keep = set(pruned.kept)
        savings = round(len(pruned.pruned) / n, 4) if n else 0.0
    else:
        keep = {patches[0].index}
        savings = 0.0
    verifs = [verify_candidate(task, pt) for pt in patches if pt.index in keep]
    best = select_best(verifs)
    return HeavySkillResult(
        task_name=task.name, engaged=engaged, n_sampled=n, n_verified=len(verifs),
        solved=any(v.pytest_passed and v.conclusive for v in verifs),
        best_index=best, total_cost=round(sum(pt.cost for pt in patches), 6),
        verify_savings_fraction=savings, candidates=verifs)
