"""Skill transfer matrix + scope learner (Alpha 30)."""

from __future__ import annotations

from acp.training.skill_transfer_matrix import (
    SkillTransferMatrix,
    TransferCell,
    transfer_verdict,
)


def test_robust_help_is_helps() -> None:
    # skill clearly lifts at decent n -> helps
    c = TransferCell("verify", "task_type:underspecified", baseline_successes=12,
                     baseline_n=30, skill_successes=28, skill_n=30)
    assert transfer_verdict(c) == "helps"


def test_clear_harm_is_hurts() -> None:
    c = TransferCell("verify", "harness:claude_code", baseline_successes=28, baseline_n=30,
                     skill_successes=12, skill_n=30)
    assert transfer_verdict(c) == "hurts"


def test_degraded_measurement_is_untrusted_not_hurts() -> None:
    # the vendor self-catch: low activation -> untrusted, never a capability/skill verdict
    c = TransferCell("verify", "harness:claude_code", baseline_successes=27, baseline_n=30,
                     skill_successes=0, skill_n=30, activation_rate=0.3)
    assert transfer_verdict(c) == "untrusted"


def test_small_sample_difference_is_neutral() -> None:
    # 3/3 vs 2/3 is not robust -> neutral, not helps
    c = TransferCell("verify", "task_type:bugfix", baseline_successes=2, baseline_n=3,
                     skill_successes=3, skill_n=3)
    assert transfer_verdict(c) == "neutral"


def test_scope_learner_includes_helps_excludes_hurts() -> None:
    m = SkillTransferMatrix()
    m.add(TransferCell("verify", "task_type:underspecified", 12, 30, 28, 30))  # helps
    m.add(TransferCell("verify", "harness:claude_code", 28, 30, 12, 30))       # hurts
    m.add(TransferCell("verify", "task_type:bugfix", 2, 3, 3, 3))              # neutral
    rec = m.recommended_scope("verify")
    assert "task_type:underspecified" in rec.include
    assert "harness:claude_code" in rec.exclude
    assert "task_type:bugfix" in rec.unknown


def test_summary_counts_verdicts() -> None:
    m = SkillTransferMatrix()
    m.add(TransferCell("s", "a", 12, 30, 28, 30))
    m.add(TransferCell("s", "b", 28, 30, 12, 30))
    s = m.summary()
    assert s["n_cells"] == 2 and s["by_verdict"].get("helps") == 1
