"""Claim checker + evidence freshness (GOALS Alpha 43 P13).

Validates each registered claim against its committed artifacts: the artifact must exist, parse,
not be flagged contaminated, satisfy any required assertions, and meet the evidence tier. A claim
that fails is reported as unsupported so docs/CI can block the overclaim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acp.reports.claim_registry import CLAIMS, Claim

# substrings that mark an artifact as contaminated/fixture-only (so it can't support a live claim)
_CONTAMINATED_KEYS = ("measurement_contaminated", "contaminated")


def _load(root: Path, rel: str) -> dict[str, Any] | None:
    p = root / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {"__unparseable__": True}


def _deep_get(obj: Any, key: str) -> Any:
    """Find `key` anywhere in a nested dict/list (first match)."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _deep_get(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_get(v, key)
            if r is not None:
                return r
    return None


def check_claim(root: Path, claim: Claim) -> dict[str, Any]:
    reasons: list[str] = []
    tiers: list[str] = []
    loaded: dict[str, dict] = {}
    for rel in claim.requires:
        data = _load(root, rel)
        if data is None:
            reasons.append(f"missing artifact: {rel}")
            continue
        if data.get("__unparseable__"):
            reasons.append(f"unparseable artifact: {rel}")
            continue
        loaded[rel] = data
        if claim.forbid_contaminated:
            for k in _CONTAMINATED_KEYS:
                if _deep_get(data, k) is True:
                    reasons.append(f"{rel} is flagged {k}=true")
        if "evidence_tier" in data:
            tiers.append(str(data["evidence_tier"]))
    # must_assert: the field must be found in AT LEAST ONE required artifact and equal expected
    # (and never contradicted by another artifact that carries it).
    for field_name, expected in claim.must_assert:
        found = [(rel, _deep_get(d, field_name)) for rel, d in loaded.items()
                 if _deep_get(d, field_name) is not None]
        if not found:
            reasons.append(f"no artifact asserts {field_name}={expected!r}")
        elif any(v != expected for _, v in found):
            bad = [f"{rel}:{v!r}" for rel, v in found if v != expected]
            reasons.append(f"{field_name} != {expected!r} in {bad}")
    # tier check: a 'live' claim cannot rest on a purely fixture-tier artifact
    if claim.tier == "live" and tiers and all("fixture" in t and "live" not in t for t in tiers):
        reasons.append(f"live claim supported only by fixture-tier evidence: {tiers}")
    return {"claim": claim.id, "text": claim.text, "supported": not reasons,
            "requires": list(claim.requires), "reasons": reasons}


def check_all(root: Path | str = ".") -> dict[str, Any]:
    root = Path(root)
    results = [check_claim(root, c) for c in CLAIMS]
    unsupported = [r for r in results if not r["supported"]]
    return {
        "experiment": "claim_evidence_map",
        "n_claims": len(results),
        "n_supported": len(results) - len(unsupported),
        "n_unsupported": len(unsupported),
        "all_supported": not unsupported,
        "claims": results,
    }
