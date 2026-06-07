"""Experience-bank / memory-policy tests (GOALS Alpha 42 P10)."""

from __future__ import annotations

from acp.memory import ExperienceBank, ExperienceEpisode, MemoryPolicy


def _ep(**kw) -> ExperienceEpisode:
    base = {"repo_family": "acme/app", "task_type": "bugfix",
            "failure_signature": "AssertionError:median", "context_strategy": "repo_map",
            "agent": "claude_harness", "reward": 1.0, "verifier_outcome": "solved",
            "privacy_scope": "tenant_a", "created_at": 0.0}
    base.update(kw)
    return ExperienceEpisode(**base)


def test_memory_write_requires_conclusive_attempt() -> None:
    bank, pol = ExperienceBank(), MemoryPolicy()
    assert not bank.write(_ep(verifier_outcome="inconclusive", reward=0.0), policy=pol)
    assert bank.write(_ep(verifier_outcome="solved"), policy=pol)
    assert bank.write(_ep(verifier_outcome="failed", reward=-1.0), policy=pol)  # negative kept
    assert len(bank.episodes) == 2


def test_negative_memory_blocks_repeated_bad_strategy() -> None:
    bank, pol = ExperienceBank(), MemoryPolicy()
    bank.write(_ep(context_strategy="minimal", verifier_outcome="failed", reward=-1.0), policy=pol)
    bank.write(_ep(context_strategy="repo_map", verifier_outcome="solved", reward=1.0), policy=pol)
    avoid = bank.avoid_strategies(tenant="tenant_a", failure_signature="AssertionError:median")
    assert "minimal" in avoid
    assert bank.recommend_strategy(
        tenant="tenant_a", failure_signature="AssertionError:median") == "repo_map"


def test_cross_tenant_memory_blocked() -> None:
    bank, pol = ExperienceBank(), MemoryPolicy()
    bank.write(_ep(privacy_scope="tenant_a"), policy=pol)
    assert bank.read(tenant="tenant_b") == []          # cross-tenant read blocked
    assert len(bank.read(tenant="tenant_a")) == 1


def test_memory_decay_changes_retrieval_ranking() -> None:
    bank, pol = ExperienceBank(), MemoryPolicy()
    bank.write(_ep(context_strategy="old_win", reward=2.0, created_at=0.0), policy=pol)
    bank.write(_ep(context_strategy="recent_win", reward=1.0, created_at=100.0), policy=pol)
    bank.decay(now=100.0, half_life=10.0)              # the old episode decays heavily
    ranked = bank.read(tenant="tenant_a")
    assert ranked[0].context_strategy == "recent_win"  # recent beats a decayed bigger reward
    # an old negative memory decays below the retrieval floor unless reconfirmed
    assert all(e.decay_score <= 1.0 for e in ranked)


def test_memory_poisoning_detector_quarantines_bad_episode() -> None:
    bank, pol = ExperienceBank(), MemoryPolicy()
    # "solved" but negative reward -> internally inconsistent -> quarantined on write
    bank.write(_ep(verifier_outcome="solved", reward=-5.0), policy=pol)
    assert bank.episodes[0].quarantined
    assert bank.read(tenant="tenant_a") == []          # quarantined episodes are not served
    # a later explicit sweep also catches a "reverted but positive reward" episode
    bank.episodes.append(_ep(post_merge_outcome="reverted", reward=3.0))
    n = bank.quarantine_poisoned(MemoryPolicy.poison_detector)
    assert n == 1
