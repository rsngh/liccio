"""Experience bank — long-lived agent memory (GOALS Alpha 42 P10).

ACP's moat is the loop over time: it should remember which (agent, context strategy, topology)
worked — and which FAILED — for a repo family / failure signature, and reuse that. Memory is a
governed subsystem (MeMo-style read/write/integrate) that ages (AgingBench: compression /
interference / revision / maintenance), is tenant-isolated, and quarantines poisoned episodes.
Deterministic and dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acp.memory.memory_policy import MemoryPolicy


@dataclass(frozen=True)
class ExperienceEpisode:
    repo_family: str
    task_type: str
    failure_signature: str          # e.g. "AssertionError:median" — the recurring symptom
    context_strategy: str
    agent: str
    repo_id: str = ""               # v2: specific repo (for same-repo vs repo-family retrieval)
    context_need: str = ""          # v2
    topology: str = "cheap_single"
    advisor_used: bool = False      # v2
    changed_symbols: tuple[str, ...] = ()
    tests_run: bool = True
    verifier_outcome: str = "solved"   # solved | failed | inconclusive
    human_review_outcome: str = "none"  # v2: approved | rejected | none
    post_merge_outcome: str = "unknown"
    reward: float = 0.0
    cost: float = 0.0
    skill_version: str = "v1"
    privacy_scope: str = "tenant_a"    # tenant/owner; cross-tenant reads are blocked
    trust_score: float = 1.0           # v2: lowered for unverified/uncertain episodes
    created_at: float = 0.0
    decay_score: float = 1.0
    quarantined: bool = False
    recipe: tuple[str, ...] = ()       # procedural memory: the winning lever SEQUENCE (Memp)

    @property
    def is_conclusive(self) -> bool:
        return self.verifier_outcome in ("solved", "failed")

    @property
    def is_negative(self) -> bool:
        return self.verifier_outcome == "failed" or self.reward < 0


@dataclass
class ExperienceBank:
    """A governed, tenant-isolated, decaying store of solve/fail episodes."""

    episodes: list[ExperienceEpisode] = field(default_factory=list)

    # --- write -------------------------------------------------------------------------
    def write(self, ep: ExperienceEpisode, *, policy: MemoryPolicy) -> bool:
        if not policy.may_write(ep):
            return False
        if policy.poison_detector(ep):
            ep = replace(ep, quarantined=True)
        self.episodes.append(ep)
        return True

    # --- read --------------------------------------------------------------------------
    def read(self, *, tenant: str, repo_family: str | None = None,
             failure_signature: str | None = None, repo_family_prefix: str | None = None,
             include_negative: bool = True, min_decay: float = 0.05) -> list[ExperienceEpisode]:
        out = []
        for ep in self.episodes:
            if ep.quarantined or ep.privacy_scope != tenant:     # tenant isolation
                continue
            if ep.decay_score < min_decay:
                continue
            family_ok = (repo_family is None or ep.repo_family == repo_family
                         or bool(repo_family_prefix
                                 and ep.repo_family.startswith(repo_family_prefix)))
            if not family_ok:
                continue
            if failure_signature is not None and ep.failure_signature != failure_signature:
                continue
            if not include_negative and ep.is_negative:
                continue
            out.append(ep)
        # rank by recency-weighted reward (decay scales reward); negatives sort to the bottom
        return sorted(out, key=lambda e: (e.reward * e.decay_score), reverse=True)

    def avoid_strategies(self, *, tenant: str, failure_signature: str) -> set[str]:
        """Negative memory: strategies that have FAILED this failure signature (and not decayed)."""
        return {e.context_strategy for e in self.read(
            tenant=tenant, failure_signature=failure_signature) if e.is_negative}

    def recommend_strategy(self, *, tenant: str, failure_signature: str) -> str | None:
        """Best positive strategy for this failure signature, avoiding known-bad ones."""
        bad = self.avoid_strategies(tenant=tenant, failure_signature=failure_signature)
        pos = [e for e in self.read(tenant=tenant, failure_signature=failure_signature,
                                    include_negative=False) if e.context_strategy not in bad]
        return pos[0].context_strategy if pos else None

    # --- aging -------------------------------------------------------------------------
    def decay(self, *, now: float, half_life: float = 10.0) -> None:
        """Exponential decay by age; reconfirmed (recent) episodes stay strong (AgingBench)."""
        for i, ep in enumerate(self.episodes):
            age = max(0.0, now - ep.created_at)
            self.episodes[i] = replace(ep, decay_score=round(0.5 ** (age / half_life), 6))

    def quarantine_poisoned(self, detector) -> int:
        n = 0
        for i, ep in enumerate(self.episodes):
            if not ep.quarantined and detector(ep):
                self.episodes[i] = replace(ep, quarantined=True)
                n += 1
        return n
