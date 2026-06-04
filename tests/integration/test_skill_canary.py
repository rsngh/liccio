"""Online A/B skill canary validation (Round 17)."""

from __future__ import annotations

from acp.training.skill_canary import evaluate_ab_canary


def _cell(success):
    return {"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
            "success": success, "status": "succeeded" if success else "failed",
            "tool_calls": 2, "commands": 1, "file_reads": 1}


def _infra():
    return {"task_type": "bugfix", "adapter": "openai_harness", "is_harness": True,
            "success": False, "status": "timed_out", "timed_out": True, "tool_calls": 0,
            "error": "timed out"}


def test_clear_lift_is_significant_and_promotes() -> None:
    control = [_cell(i < 6) for i in range(20)]   # 30% solve
    canary = [_cell(True) for _ in range(20)]      # 100% solve
    res = evaluate_ab_canary(control, canary)
    assert res.lift > 0 and res.significant and res.promote
    assert res.p_value < 0.05


def test_no_lift_does_not_promote() -> None:
    control = [_cell(i < 15) for i in range(20)]
    canary = [_cell(i < 15) for i in range(20)]
    res = evaluate_ab_canary(control, canary)
    assert not res.promote and not res.significant


def test_contaminated_arm_blocks_promotion() -> None:
    control = [_cell(True) for _ in range(2)] + [_infra() for _ in range(5)]
    canary = [_cell(True) for _ in range(7)]
    res = evaluate_ab_canary(control, canary)
    # Control's infra share contaminates it -> promotion blocked regardless of lift.
    assert res.contaminated and not res.promote
    assert any("contaminated" in r for r in res.reasons)


def test_small_sample_blocks_promotion() -> None:
    control = [_cell(False) for _ in range(3)]
    canary = [_cell(True) for _ in range(3)]
    res = evaluate_ab_canary(control, canary, min_per_arm=5)
    assert not res.promote and any("insufficient" in r for r in res.reasons)


def test_min_lift_threshold_enforced() -> None:
    control = [_cell(i < 16) for i in range(20)]   # 80%
    canary = [_cell(i < 17) for i in range(20)]    # 85% — small lift
    res = evaluate_ab_canary(control, canary, min_lift=0.2)
    assert not res.promote and any("min_lift" in r for r in res.reasons)
