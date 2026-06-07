"""AdvisorPolicy v2 calibration tests (GOALS Alpha 43 P2)."""

from __future__ import annotations

from acp.finops.advisor_marginal_value import advisor_marginal_value, is_advisor_waste
from acp.routing.advisor_calibration import AdvisorCalibrator


def test_advisor_called_only_when_marginal_value_positive() -> None:
    # big uplift on a valued task -> call
    d = advisor_marginal_value(p_solve_without_advisor=0.4, p_solve_with_advisor=0.8,
                               advisor_cost=0.002, budget_class="normal_bugfix")
    assert d.should_call and d.expected_marginal_value > 0
    # negligible uplift -> do not call (waste)
    d2 = advisor_marginal_value(p_solve_without_advisor=0.79, p_solve_with_advisor=0.80,
                                advisor_cost=0.05, budget_class="cheap_docs")
    assert not d2.should_call


def test_calibrator_learns_uplift_and_recommends() -> None:
    cells = (
        [{"bucket": "xfile", "solved_cheap": False, "advisor_used": True, "solved_after": True}] * 6
        + [{"bucket": "xfile", "solved_cheap": False, "advisor_used": False,
            "solved_after": False}] * 4
    )
    cal = AdvisorCalibrator().fit(cells)
    rec = cal.should_consult(bucket="xfile", budget_class="cross_file_bugfix")
    assert rec["should_consult"]                 # advisor lifts xfile from ~0 -> high
    assert rec["p_with_advisor"] > rec["base_rate"]


def test_no_uplift_bucket_not_escalated() -> None:
    cells = [{"bucket": "easy", "solved_cheap": True, "advisor_used": False,
              "solved_after": True}] * 10
    cal = AdvisorCalibrator().fit(cells)
    rec = cal.should_consult(bucket="easy", budget_class="cheap_docs")
    assert not rec["should_consult"]             # already solved cheaply -> no value


def test_trigger_quality_flags_waste() -> None:
    cells = [
        {"bucket": "b", "advisor_used": True, "solved_cheap": False, "solved_after": True},
        {"bucket": "b", "advisor_used": True, "solved_cheap": True, "solved_after": True},  # waste
        {"bucket": "b", "advisor_used": True, "solved_cheap": False,
         "solved_after": False},  # waste
    ]
    q = AdvisorCalibrator().trigger_quality(cells)
    assert q["n_advised"] == 3
    assert q["advisor_precision"] == round(1 / 3, 4)


def test_is_advisor_waste() -> None:
    assert is_advisor_waste(solved_without_advisor=True, solved_with_advisor=True)
    assert not is_advisor_waste(solved_without_advisor=False, solved_with_advisor=True)
