"""Infra-flake taxonomy: classify infrastructure events, never as failures (Alpha 25).

Measurement-trust requires that an infrastructure event — a Docker daemon that vanishes, a
provider 429, a vendor CLI that is not installed or hangs, pytest-in-pytest contention — is
recorded as INFRA/inconclusive, NOT as a model capability failure, a skill failure, or a
learning-table update. This module gives every such event a typed classification with the
exact booleans the rest of the system keys on, plus a health signal, so CI and health can
report infra events in a controlled way rather than as red test failures.
"""

from __future__ import annotations

from dataclasses import dataclass

INFRA_EVENTS = (
    "docker_unavailable_before_run", "docker_unavailable_mid_run",
    "pytest_in_pytest_contention", "provider_timeout", "provider_rate_limit_429",
    "vendor_cli_not_installed", "vendor_cli_hang",
)

# Health signal each event maps to (what an operator sees).
_HEALTH = {
    "docker_unavailable_before_run": "docker_skipped",
    "docker_unavailable_mid_run": "docker_degraded",
    "pytest_in_pytest_contention": "test_contention",
    "provider_timeout": "provider_degraded",
    "provider_rate_limit_429": "provider_throttled",
    "vendor_cli_not_installed": "vendor_unavailable",
    "vendor_cli_hang": "vendor_degraded",
}


@dataclass
class InfraClassification:
    event: str
    is_infra: bool
    is_model_failure: bool
    is_skill_failure: bool
    is_capability_update: bool      # may this update the capability/solve-rate table?
    conclusive: bool                # does this attempt carry trustworthy task signal?
    health_signal: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def classify_infra_event(event: str) -> InfraClassification:
    """Classify an infrastructure event. Every infra event is non-failure, inconclusive."""
    if event not in INFRA_EVENTS:
        raise ValueError(f"unknown infra event {event}")
    return InfraClassification(
        event=event, is_infra=True, is_model_failure=False, is_skill_failure=False,
        is_capability_update=False, conclusive=False, health_signal=_HEALTH[event])


def attempt_outcome_for(event: str) -> str:
    """Map an infra event to the AttemptOutcome value used by the measurement layer."""
    mapping = {
        "docker_unavailable_before_run": "inconclusive",
        "docker_unavailable_mid_run": "inconclusive",
        "pytest_in_pytest_contention": "inconclusive",
        "provider_timeout": "infra_timeout_before_action",
        "provider_rate_limit_429": "provider_rate_limit",
        "vendor_cli_not_installed": "inconclusive",
        "vendor_cli_hang": "infra_timeout_before_action",
    }
    return mapping[event]


def summarize_infra(events: list) -> dict:
    """Roll a list of infra events into a health-facing summary (counts by signal)."""
    from collections import Counter
    classes = [classify_infra_event(e) for e in events]
    by_signal = Counter(c.health_signal for c in classes)
    return {"n_events": len(events), "by_signal": dict(by_signal),
            "all_infra": all(c.is_infra for c in classes),
            "any_capability_update": any(c.is_capability_update for c in classes),
            "any_model_failure": any(c.is_model_failure for c in classes)}
