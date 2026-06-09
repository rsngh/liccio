"""Verification layer: plans, detectors, runners, evidence aggregation."""

from acp.verification.aggregate import AggregateVerdict, EvidenceAggregator
from acp.verification.detectors import ProjectProfile, detect
from acp.verification.plan import build_plan
from acp.verification.proxy_stop_signal import (
    ProxyHealth,
    ProxyStopSignal,
    decide,
    proxy_health_by_family,
)
from acp.verification.service import VerificationService

__all__ = [
    "AggregateVerdict",
    "EvidenceAggregator",
    "ProjectProfile",
    "ProxyHealth",
    "ProxyStopSignal",
    "VerificationService",
    "build_plan",
    "decide",
    "detect",
    "proxy_health_by_family",
]
