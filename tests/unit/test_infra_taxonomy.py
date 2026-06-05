"""Infra-flake classification (Alpha 25, test B).

Every infrastructure event must classify as infra/inconclusive — never a model failure, a
skill failure, or a capability/solve-rate update — and surface a health signal.
"""

from __future__ import annotations

import pytest

from acp.evaluation.infra_taxonomy import (
    INFRA_EVENTS,
    attempt_outcome_for,
    classify_infra_event,
    summarize_infra,
)


@pytest.mark.parametrize("event", INFRA_EVENTS)
def test_every_infra_event_is_non_failure_and_inconclusive(event) -> None:
    c = classify_infra_event(event)
    assert c.is_infra and not c.is_model_failure and not c.is_skill_failure
    assert not c.is_capability_update      # never updates the solve-rate table
    assert not c.conclusive                # carries no trustworthy task signal
    assert c.health_signal                 # operator-visible


def test_specific_events_map_as_expected() -> None:
    assert classify_infra_event("docker_unavailable_mid_run").health_signal == "docker_degraded"
    assert classify_infra_event("vendor_cli_not_installed").health_signal == "vendor_unavailable"
    assert attempt_outcome_for("provider_rate_limit_429") == "provider_rate_limit"
    assert attempt_outcome_for("docker_unavailable_before_run") == "inconclusive"


def test_summary_never_reports_model_failure_or_capability_update() -> None:
    s = summarize_infra(["docker_unavailable_mid_run", "provider_timeout",
                         "vendor_cli_hang", "pytest_in_pytest_contention"])
    assert s["n_events"] == 4 and s["all_infra"]
    assert not s["any_capability_update"] and not s["any_model_failure"]
    assert s["by_signal"]["docker_degraded"] == 1


def test_unknown_event_rejected() -> None:
    with pytest.raises(ValueError):
        classify_infra_event("model_was_just_bad")
