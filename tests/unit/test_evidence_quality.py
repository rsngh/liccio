"""Evidence tiers + activation-aware solve-rate denominators (Round 25)."""

from __future__ import annotations

from acp.evaluation.evidence_quality import (
    EvidenceTier,
    solve_rate_breakdown,
    stamp_evidence,
    weakest_tier,
)


def _cell(success, activated, conclusive=True, mq=1.0):
    # status drives classify_attempt; harness no-op (not activated) -> activation failure
    return {"success": success, "is_harness": True,
            "tool_calls": 1 if activated else 0,
            "diff_captured": activated,
            "status": "succeeded" if success else "failed",
            "timed_out": False, "error": None, "measurement_quality": mq}


def test_weakest_tier_dominates() -> None:
    assert weakest_tier(["live_api", "synthetic", "vendor_native_live"]) == \
        EvidenceTier.SYNTHETIC
    assert weakest_tier(["vendor_native_live", "live_api"]) == EvidenceTier.LIVE_API


def test_four_denominators_are_explicit() -> None:
    # 4 solved, 1 conclusive-fail (activated), 1 no-op (activation failure, not activated)
    cells = [_cell(True, True), _cell(True, True), _cell(True, True), _cell(True, True),
             _cell(False, True), _cell(False, False)]
    b = solve_rate_breakdown(cells)
    assert b.n_all == 6
    assert b.n_activated == 5            # the no-op is excluded from activated
    assert b.solve_rate_all == round(4 / 6, 4)
    assert b.solve_rate_activated == round(4 / 5, 4)    # over activated only
    # the no-op counts as a CONCLUSIVE activation failure (enum), so conclusive n=6 and the
    # conclusive rate (0.667) is LOWER than the activated rate (0.8) — exactly the
    # denominator distinction the review demands be explicit.
    assert b.n_conclusive == 6 and b.solve_rate_conclusive == round(4 / 6, 4)
    assert b.solve_rate_activated > b.solve_rate_conclusive


def test_trusted_activated_excludes_low_quality() -> None:
    cells = [_cell(True, True, mq=1.0), _cell(True, True, mq=0.3)]  # second untrusted
    b = solve_rate_breakdown(cells, min_quality=0.7)
    assert b.n_trusted_activated == 1 and b.solve_rate_trusted_activated == 1.0
    assert b.n_activated == 2


def test_no_op_arm_does_not_inflate_or_deflate_capability() -> None:
    # an all-no-op arm: activated denominator is 0 -> activated rate 0, not a 0% capability
    cells = [_cell(False, False), _cell(False, False)]
    b = solve_rate_breakdown(cells)
    assert b.n_activated == 0 and b.solve_rate_activated == 0.0
    assert b.solve_rate_all == 0.0


def test_stamp_evidence() -> None:
    r = stamp_evidence({"experiment": "x"}, EvidenceTier.LIVE_API)
    assert r["evidence_tier"] == "live_api"
    assert stamp_evidence({}, "vendor_native_live")["evidence_tier"] == "vendor_native_live"
