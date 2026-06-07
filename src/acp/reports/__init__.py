"""Claim checker + evidence freshness (GOALS Alpha 43 P13): every headline claim must map to
fresh, uncontaminated, right-tier committed evidence, or it is reported as unsupported."""

from acp.reports.claim_checker import check_all, check_claim
from acp.reports.claim_registry import CLAIMS, Claim

__all__ = ["check_all", "check_claim", "CLAIMS", "Claim"]
