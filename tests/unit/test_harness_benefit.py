"""Harness-benefit training loop (Alpha 40)."""

from __future__ import annotations

from acp.training.harness_benefit import (
    HarnessBenefitRecord,
    adherence_decay_benchmark,
    build_activation_dataset,
    build_adherence_dataset,
    pass_when_loaded_report,
)


def _r(adapter, loaded, activated, followed, solved, phase=0):
    return HarnessBenefitRecord(adapter, loaded, activated, followed, solved, phase)


def test_har_hfr_pwl_are_distinct() -> None:
    recs = [
        _r("weak", True, False, False, False),   # loaded but NOT activated
        _r("weak", True, True, False, False),     # activated but NOT followed
        _r("weak", True, True, True, True),       # activated + followed + solved
        _r("weak", True, True, True, False),      # activated + followed but failed
    ]
    rep = pass_when_loaded_report(recs)["by_adapter"]["weak"]
    assert rep["har"] == 0.75      # 3/4 activated
    assert rep["hfr"] == round(2 / 3, 4)   # 2/3 of activated followed
    assert rep["pwl"] == 0.25      # 1/4 loaded solved


def test_activation_dataset_labels_activation() -> None:
    recs = [_r("a", True, True, True, True), _r("a", True, False, False, False),
            _r("a", False, False, False, False)]  # not loaded -> excluded
    ds = build_activation_dataset(recs)
    assert len(ds) == 2 and [e["target"] for e in ds] == [1, 0]


def test_adherence_dataset_only_activated() -> None:
    recs = [_r("a", True, True, True, True), _r("a", True, False, False, False)]
    ds = build_adherence_dataset(recs)
    assert len(ds) == 1 and ds[0]["target"] == 1


def test_adherence_decay_flagged() -> None:
    # phase 0 high adherence, phase 2 low -> decay
    recs = ([_r("a", True, True, True, True, phase=0)] * 4
            + [_r("a", True, True, False, False, phase=2)] * 3)
    out = adherence_decay_benchmark(recs)
    assert out["adherence_decays"] and out["first_to_last_drop"] > 0
    assert out["hfr_by_phase"][0] > out["hfr_by_phase"][2]
