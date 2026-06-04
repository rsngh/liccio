"""Cross-harness transfer study analysis (Alpha 21 WS13)."""

from __future__ import annotations

from acp.training.skill_transfer_study import TransferObservation, run_transfer_study


def test_portable_skill_recommends_broaden() -> None:
    obs = TransferObservation("openai_harness", "claude_harness", target_baseline=0.5,
                              target_with_skill=1.0, source_lift=0.5)
    study = run_transfer_study("verify", [obs])
    assert study.verdicts[0].portable and not study.verdicts[0].negative_transfer
    assert "broaden" in study.scope_recommendation


def test_negative_transfer_recommends_narrow() -> None:
    obs = TransferObservation("openai_harness", "claude_harness", target_baseline=0.8,
                              target_with_skill=0.5, source_lift=0.5)
    study = run_transfer_study("verify", [obs])
    assert study.verdicts[0].negative_transfer
    assert "narrow" in study.scope_recommendation


def test_weak_transfer_keeps_source_scope() -> None:
    obs = TransferObservation("openai_harness", "claude_harness", target_baseline=0.5,
                              target_with_skill=0.55, source_lift=0.5)  # tiny gain
    study = run_transfer_study("verify", [obs])
    assert not study.verdicts[0].portable and not study.verdicts[0].negative_transfer
    assert "keep source-scoped" in study.scope_recommendation


def test_null_transfer_matches_round16_live() -> None:
    # Mirrors the honest R16 live result: gain 0.0 -> not portable, not negative.
    obs = TransferObservation("openai_harness", "claude_harness", target_baseline=0.333,
                              target_with_skill=0.333, source_lift=0.5)
    v = run_transfer_study("verify", [obs]).verdicts[0]
    assert v.transfer_gain == 0.0 and not v.portable and not v.negative_transfer
