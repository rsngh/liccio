"""Claim checker tests (GOALS Alpha 43 P13) — deterministic, synthetic artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from acp.reports.claim_checker import check_all, check_claim
from acp.reports.claim_registry import Claim


def _write(root: Path, rel: str, data: dict) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


def test_missing_artifact_makes_claim_unsupported(tmp_path) -> None:
    c = Claim("x", "x", requires=("reports/x.json",))
    r = check_claim(tmp_path, c)
    assert not r["supported"] and "missing artifact" in r["reasons"][0]


def test_contaminated_artifact_blocks_claim(tmp_path) -> None:
    _write(tmp_path, "reports/x.json", {"measurement_contaminated": True})
    c = Claim("x", "x", requires=("reports/x.json",))
    r = check_claim(tmp_path, c)
    assert not r["supported"] and any("contaminated" in s for s in r["reasons"])


def test_must_assert_enforced(tmp_path) -> None:
    _write(tmp_path, "reports/x.json", {"helps": False})
    c = Claim("x", "x", requires=("reports/x.json",), must_assert=(("helps", True),))
    assert not check_claim(tmp_path, c)["supported"]
    _write(tmp_path, "reports/x.json", {"helps": True})
    assert check_claim(tmp_path, c)["supported"]


def test_live_claim_cannot_rest_on_fixture_only(tmp_path) -> None:
    _write(tmp_path, "reports/x.json", {"evidence_tier": "fixture-only"})
    c = Claim("x", "x", requires=("reports/x.json",), tier="live")
    assert not check_claim(tmp_path, c)["supported"]


def test_supported_claim_passes(tmp_path) -> None:
    _write(tmp_path, "reports/x.json", {"helps": True, "evidence_tier": "live"})
    c = Claim("x", "x", requires=("reports/x.json",), tier="live",
              must_assert=(("helps", True),))
    assert check_claim(tmp_path, c)["supported"]


def test_check_all_returns_summary(tmp_path) -> None:
    out = check_all(tmp_path)        # no artifacts -> all unsupported, but structure is sound
    assert out["n_claims"] >= 6 and out["n_unsupported"] == out["n_claims"]
    assert out["all_supported"] is False
