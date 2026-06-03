"""Harness availability audit schema (Alpha 11/12 WS3).

Encodes the live-bakeoff lesson that a harness can be *silently absent*: a cached
settings singleton hid claude_harness even though its key was present. The audit
makes "expected but missing" a loud, health-degrading condition.
"""

from __future__ import annotations

from pydantic import Field

from acp.schemas.base import ACPModel


class HarnessAvailabilityReport(ACPModel):
    """Which harnesses were expected (key present) vs actually available.

    ``silently_absent`` is the dangerous set: expected from credentials but not
    built/healthy. Any non-empty ``silently_absent`` sets ``degraded`` true.
    """

    expected: list[str] = Field(default_factory=list)
    available: list[str] = Field(default_factory=list)
    unavailable_reasons: dict[str, str] = Field(default_factory=dict)
    silently_absent: list[str] = Field(default_factory=list)
    degraded: bool = False
