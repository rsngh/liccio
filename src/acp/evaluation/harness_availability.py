"""Harness availability audit (Alpha 11/12 WS3).

Compares the harnesses that *should* exist given available credentials against the
harnesses that are actually built and healthy, so a silently-absent harness (the
cached-settings bug) becomes a loud, health-degrading signal instead of a quietly
shorter bakeoff.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from acp.schemas.harness_availability import HarnessAvailabilityReport

# Which env var gates each ACP-native harness.
HARNESS_KEYS: dict[str, str] = {
    "openai_harness": "OPENAI_API_KEY",
    "claude_harness": "ANTHROPIC_API_KEY",
}


def expected_harnesses(env: Mapping[str, str] | None = None) -> list[str]:
    """Harnesses that should be available given the credentials in ``env``."""
    e = os.environ if env is None else env
    return sorted(name for name, key in HARNESS_KEYS.items() if e.get(key))


def audit_harness_availability(
    available: Mapping[str, bool] | set[str] | list[str],
    *,
    env: Mapping[str, str] | None = None,
    unavailable_reasons: Mapping[str, str] | None = None,
) -> HarnessAvailabilityReport:
    """Audit availability against credential-derived expectations.

    ``available`` is the set/mapping of harness names that actually built and
    passed healthcheck. A harness that is expected (its key is set) but not in
    ``available`` is ``silently_absent`` and degrades health.
    """
    if isinstance(available, Mapping):
        avail = {n for n, ok in available.items() if ok}
    else:
        avail = set(available)
    expected = expected_harnesses(env)
    reasons = dict(unavailable_reasons or {})
    silently_absent = [h for h in expected if h not in avail]
    for h in silently_absent:
        reasons.setdefault(h, "expected (key present) but not built/healthy")
    return HarnessAvailabilityReport(
        expected=expected,
        available=sorted(avail),
        unavailable_reasons=reasons,
        silently_absent=silently_absent,
        degraded=bool(silently_absent),
    )
