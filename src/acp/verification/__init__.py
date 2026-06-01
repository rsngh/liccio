"""Verification layer: plans, detectors, runners, evidence aggregation."""

from acp.verification.aggregate import AggregateVerdict, EvidenceAggregator
from acp.verification.detectors import ProjectProfile, detect
from acp.verification.plan import build_plan
from acp.verification.service import VerificationService

__all__ = [
    "AggregateVerdict",
    "EvidenceAggregator",
    "ProjectProfile",
    "VerificationService",
    "build_plan",
    "detect",
]
