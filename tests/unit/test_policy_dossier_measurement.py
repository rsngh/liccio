"""Policy dossier v2 measurement section (Alpha 11/12 WS9)."""

from __future__ import annotations

from acp.core.policy_dossier import PolicyDecisionDossier, attach_measurement_quality


def _dossier():
    return PolicyDecisionDossier(run_id="r1", task_id="t1", viability=None,
                                 chosen_action={"agent_name": "openai_harness"})


def test_clean_measurement_is_trustworthy() -> None:
    cells = [{"adapter": "openai_harness", "success": True, "status": "succeeded",
              "tool_calls": 2, "is_harness": True} for _ in range(5)]
    d = attach_measurement_quality(_dossier(), cells)
    assert d.measurement_quality["trustworthy"]
    assert d.measurement_quality["solve_rate_conclusive"] == 1.0


def test_contaminated_measurement_flagged_and_noted() -> None:
    cells = [{"adapter": "openai_harness", "success": True, "status": "succeeded",
              "tool_calls": 2, "is_harness": True}] + [
        {"adapter": "openai_harness", "success": False, "status": "timed_out",
         "timed_out": True, "tool_calls": 0, "error": "timed out", "is_harness": True}
        for _ in range(4)]
    d = attach_measurement_quality(_dossier(), cells)
    assert not d.measurement_quality["trustworthy"]
    assert d.measurement_quality["contaminated"]
    assert any("contaminated" in n for n in d.notes)
