"""Battery-v2 semantics: validity, acceptance bar, mutation sensitivity, fail-to-pass gating."""

from __future__ import annotations

import ast
from pathlib import Path

from acp.verification import property_checks, repair_battery
from acp.verification.battery_mutation import gen_mutants, sensitivity_weights
from acp.verification.repair_battery import (
    BatteryScore,
    RepairBattery,
    _keep_by_baseline,
    build_battery_v2,
    score_candidate,
)

_BUGGY = "def add(a, b):\n    return a - b\n"          # the classic wrong-operator bug
_PUBLIC = "from m import add\n\ndef test_pub():\n    assert add(1, 1) == 2\n"
_DISC = "from m import add\n\ndef test_d():\n    assert add(2, 1) == 3\n"   # fails on buggy
_GUARD = "from m import add\n\ndef test_g():\n    assert add(0, 0) == 0\n"  # passes on buggy
_JUNK = "def test_j():\n    assert True\n"                                   # insensitive


def _battery(tmp_path: Path, *, valid: bool = True,
             weights: list[float] | None = None) -> RepairBattery:
    return RepairBattery(checks=[("example", _DISC), ("example", _GUARD), ("example", _JUNK)],
                         baseline_pass=[False, True, True], public_test=_PUBLIC,
                         module_path="m.py", extra_files={}, valid=valid,
                         invalid_reason="" if valid else "non_discriminating",
                         check_weights=weights or [])


def test_invalid_battery_never_scores_one(tmp_path: Path) -> None:
    bat = _battery(tmp_path, valid=False)
    gold = "def add(a, b):\n    return a + b\n"
    sc = score_candidate(bat, candidate_src=gold, workspace_root=tmp_path, candidate_id="g")
    assert not sc.battery_valid
    assert sc.score <= 0.11          # capped at the public contribution — never a vacuous 1.0
    assert not sc.accept()


def test_accept_tolerates_minority_wrong_checks() -> None:
    # 9/10 weighted discriminating + all guards -> accept; the old all-checks bar would reject
    sc = BatteryScore(candidate_id="x", score=0.95, public_pass=True, adversarial_high=False,
                      n_discrim_surviving=10, n_discrim_passed=9, n_guard_surviving=3,
                      n_guard_passed=3, disc_frac=0.9, guard_frac=1.0, battery_valid=True)
    assert sc.accept()
    assert not sc.proxy_pass
    sc_bad = BatteryScore(candidate_id="y", score=0.5, public_pass=True, adversarial_high=False,
                          n_discrim_surviving=10, n_discrim_passed=5, n_guard_surviving=3,
                          n_guard_passed=3, disc_frac=0.5, guard_frac=1.0, battery_valid=True)
    assert not sc_bad.accept()
    sc_one = BatteryScore(candidate_id="z", score=1.0, public_pass=True, adversarial_high=False,
                          n_discrim_surviving=1, n_discrim_passed=1, n_guard_surviving=0,
                          n_guard_passed=0, disc_frac=1.0, guard_frac=1.0, battery_valid=True)
    assert not sc_one.accept()       # needs >=2 surviving discriminating checks


def test_weighted_score_and_gold_accept(tmp_path: Path) -> None:
    bat = _battery(tmp_path, weights=[1.0, 1.0, 0.1])
    gold = "def add(a, b):\n    return a + b\n"
    sc = score_candidate(bat, candidate_src=gold, workspace_root=tmp_path, candidate_id="g")
    assert sc.public_pass and sc.disc_frac == 1.0 and sc.guard_frac == 1.0
    buggy_sc = score_candidate(bat, candidate_src=_BUGGY, workspace_root=tmp_path, candidate_id="b")
    assert buggy_sc.disc_frac == 0.0 and not buggy_sc.accept()


def test_gen_mutants_parse_safe_and_distinct() -> None:
    src = "def clamp(x, lo, hi):\n    if x < lo:\n        return lo\n    return min(x + 1, hi)\n"
    muts = gen_mutants(src, None, cap=10)
    assert muts
    for m in muts:
        ast.parse(m)
        assert m != src


def test_sensitivity_weights_flag_insensitive_checks(tmp_path: Path) -> None:
    checks = [("example", _DISC), ("example", _JUNK)]
    weights, info = sensitivity_weights(_BUGGY, checks, [False, True], module_path="m.py",
                                        extra_files={}, root=tmp_path, spans=None, cap=8)
    assert info["n_mutants"] > 0
    # the a-b -> a+b mutant flips the discriminating check to PASS; junk never reacts
    assert weights[0] > weights[1]


class _Spec:
    def __init__(self) -> None:
        self.issue_text = "add(a, b) should return the sum a + b"
        self.public_test = _PUBLIC
        self.module_path = "m.py"


# three distinct metamorphic properties, each FALSIFIED by the a-b bug but satisfied by a+b gold
_P_COMMUTE = (
    "from hypothesis import given, strategies as st\nimport m\n"
    "@given(st.integers(min_value=-50, max_value=50), st.integers(min_value=-50, max_value=50))\n"
    "def test_commute(a, b):\n    assert m.add(a, b) == m.add(b, a)\n"
)
_P_SHIFT = (   # add(a, b-1) + 1 == add(a, b) on gold; on buggy a-(b-1)+1 = a-b+2 != a-b
    "from hypothesis import given, strategies as st\nimport m\n"
    "@given(st.integers(min_value=-50, max_value=50), st.integers(min_value=-50, max_value=50))\n"
    "def test_shift(a, b):\n    assert m.add(a, b - 1) + 1 == m.add(a, b)\n"
)
_P_DIFF = (   # add(a,b)-add(a,c) == b-c on gold; on buggy (a-b)-(a-c) = c-b
    "from hypothesis import given, strategies as st\nimport m\n"
    "@given(st.integers(min_value=-50, max_value=50), st.integers(min_value=-50, max_value=50),\n"
    "       st.integers(min_value=-50, max_value=50))\n"
    "def test_diff(a, b, c):\n    assert m.add(a, b) - m.add(a, c) == b - c\n"
)


def test_pbt_phase_admits_discriminating_props_and_gold_accepts(tmp_path, monkeypatch) -> None:
    # P12 W1: when example/flip generation leaves the battery thin, the PBT phase lets Hypothesis
    # search the inputs that break a property — admitting only those FALSIFIED on buggy — so the
    # battery becomes valid and the gold fix still accepts (buggy must not).
    monkeypatch.setattr(repair_battery, "_generate", lambda *a, **k: ([], 0.0))  # no example checks
    monkeypatch.setattr(repair_battery, "_entailment_filter", lambda *a, **k: ([], 0.0))  # no flags
    monkeypatch.setattr(property_checks, "generate_properties",
                        lambda *a, **k: ([_P_COMMUTE, _P_SHIFT, _P_DIFF], 0.0))
    bat = build_battery_v2(_Spec(), client=object(), module_path="m.py", extra_files={},
                           baseline_src=_BUGGY, public_test=_PUBLIC,
                           workspace_root=tmp_path / "b", focus_src=_BUGGY,
                           mutant_cap=6, rebuilds_on_invalid=0)
    assert any(k == "pbt" for k, _ in bat.checks)      # PBT phase wired into the battery
    assert bat.n_discriminating >= 3 and bat.valid     # proven discriminators -> valid
    gold = "def add(a, b):\n    return a + b\n"
    gsc = score_candidate(bat, candidate_src=gold, workspace_root=tmp_path / "g",
                          candidate_id="g")
    assert gsc.accept()
    bsc = score_candidate(bat, candidate_src=_BUGGY, workspace_root=tmp_path / "x",
                          candidate_id="x")
    assert not bsc.accept()


def test_pbt_phase_off_skips_property_search(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(repair_battery, "_generate", lambda *a, **k: ([], 0.0))
    monkeypatch.setattr(repair_battery, "_entailment_filter", lambda *a, **k: ([], 0.0))
    called = {"n": 0}
    def _spy(*a, **k):
        called["n"] += 1
        return ([_P_COMMUTE], 0.0)
    monkeypatch.setattr(property_checks, "generate_properties", _spy)
    build_battery_v2(_Spec(), client=object(), module_path="m.py", extra_files={},
                     baseline_src=_BUGGY, public_test=_PUBLIC, workspace_root=tmp_path / "b",
                     focus_src=_BUGGY, mutant_cap=4, rebuilds_on_invalid=0, use_pbt=False)
    assert called["n"] == 0       # use_pbt=False fully gates the property search off


def test_fail_to_pass_gate(tmp_path: Path) -> None:
    kept = _keep_by_baseline([_DISC, _GUARD], want_fail=True, module_path="m.py",
                             baseline_src=_BUGGY, extra_files={}, root=tmp_path, kind="f2p")
    assert [s for _k, s in kept] == [_DISC]      # only the check that FAILS on buggy is admitted
    pins = _keep_by_baseline([_DISC, _GUARD], want_fail=False, module_path="m.py",
                             baseline_src=_BUGGY, extra_files={}, root=tmp_path, kind="pin")
    assert [s for _k, s in pins] == [_GUARD]     # pin path keeps only buggy-passers
