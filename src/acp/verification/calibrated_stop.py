# ruff: noqa: E501
"""Calibrated commit/abstain for tasks hidden tests can't grade (Sufficient Context 2411.06037).

Phase-1's proxy verifier needs *runnable* tests. For work tests can't score (large-repo orientation,
ambiguous specs, perf), the router's stop-signal must be a calibrated confidence + abstention:
Sufficient Context shows models are wrong even with sufficient context, so committing on weak
evidence is the failure mode. This decides commit / abstain / human-review from a verifier/judge
confidence and a context-sufficiency score, with a stricter bar on high risk — trading coverage for
PRECISION (never a confident-but-wrong auto-commit).

Deterministic, dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass

_THRESH = {"low": 0.6, "medium": 0.7, "high": 0.85, "critical": 0.9}


@dataclass
class StopDecision:
    action: str          # commit | abstain | human_review
    confidence: float
    reason: str


def calibrated_stop(*, judge_confidence: float, sufficiency_score: float,
                    risk_level: str = "low") -> StopDecision:
    """Commit only if the combined confidence clears the risk-calibrated bar AND context is sufficient."""
    bar = _THRESH.get(risk_level, 0.7)
    combined = round(min(judge_confidence, 0.5 + 0.5 * sufficiency_score), 4)  # sufficiency caps confidence
    if sufficiency_score < 0.4:
        return StopDecision("human_review", combined, "insufficient context")
    if combined >= bar:
        return StopDecision("commit", combined, f"confidence {combined} >= {bar}")
    # confident-enough to attempt but not to auto-commit -> abstain (low risk) or human (high risk)
    high = risk_level in ("high", "critical")
    return StopDecision("human_review" if high else "abstain", combined,
                        f"confidence {combined} < {bar}")
