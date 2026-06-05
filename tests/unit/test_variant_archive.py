"""DGM-style governed variant archive (Alpha 24 area 13)."""

from __future__ import annotations

from acp.training.variant_archive import (
    Variant,
    VariantArchive,
    evolve,
    novelty_score,
    safety_check,
)


def test_unsafe_variants_are_rejected_not_archived() -> None:
    arc = VariantArchive()
    assert not arc.add(Variant("a", {"sandbox": True, "disable_secret_scan": True}))
    assert not arc.add(Variant("b", {"sandbox": True, "skip_verification": True}))
    assert not arc.add(Variant("c", {"sandbox": False}))  # no sandbox
    assert len(arc.variants) == 0 and len(arc.rejected) == 3
    assert all(v.reject_reason for v in arc.rejected)


def test_safe_variant_is_archived_with_novelty() -> None:
    arc = VariantArchive()
    assert arc.add(Variant("a", {"sandbox": True, "x": 1.0}, score=0.5))
    assert arc.variants[0].novelty == 1.0  # first variant is maximally novel


def test_high_risk_variant_flags_human_review() -> None:
    arc = VariantArchive()
    arc.add(Variant("a", {"sandbox": True, "risk": "high", "x": 1.0}))
    assert arc.variants[0].requires_human_review


def test_novelty_grows_with_distance() -> None:
    base = [Variant("a", {"sandbox": True, "x": 0.0})]
    near = novelty_score(Variant("b", {"sandbox": True, "x": 0.1}), base)
    far = novelty_score(Variant("c", {"sandbox": True, "x": 5.0}), base)
    assert far > near


def test_evolution_finds_improvement_safely() -> None:
    # objective peaks at x=10; propose nudges x toward the parent's neighborhood
    def eval_fn(p):
        return -abs(p.get("x", 0.0) - 10.0)

    def propose(parent, c):
        return {"sandbox": True, "x": parent.get("x", 0.0) + (c + 1)}

    arc = evolve({"sandbox": True, "x": 0.0}, propose_fn=propose, eval_fn=eval_fn,
                 generations=5, children_per_gen=3)
    best = arc.best()
    assert best is not None and best.score > eval_fn({"x": 0.0})  # improved over seed
    assert all(safety_check(v)[0] for v in arc.variants)          # archive is all-safe


def test_parent_selection_blends_score_and_novelty() -> None:
    arc = VariantArchive()
    arc.add(Variant("a", {"sandbox": True, "x": 0.0}, score=1.0))
    arc.add(Variant("b", {"sandbox": True, "x": 9.0}, score=0.9))
    parents = arc.select_parents(k=1)
    assert len(parents) == 1
