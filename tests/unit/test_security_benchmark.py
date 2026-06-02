"""Tests for the security & prompt-injection benchmark (Alpha-8 WS18)."""

from __future__ import annotations

import json

from acp.evaluation.security_benchmark import DEFAULT_SECRET, run_security_benchmark


def test_every_attack_is_escalated_or_flagged() -> None:
    report = run_security_benchmark()
    assert report["summary"]["n_attacks"] > 0
    for r in report["results"]:
        assert r["escalated"] or r["detector_flagged"], r["attack"]
    assert report["summary"]["all_handled"] is True


def test_no_secret_leaks_in_any_attack() -> None:
    report = run_security_benchmark()
    assert report["summary"]["any_secret_leak"] is False
    assert all(r["secret_leaked"] is False for r in report["results"])
    # The planted secret must not survive anywhere in the serialized report.
    assert DEFAULT_SECRET not in json.dumps(report)


def test_malicious_patches_flagged_by_adversarial_detector() -> None:
    report = run_security_benchmark()
    by_name = {r["attack"]: r for r in report["results"]}
    for name in ("delete_tests", "disable_verification", "write_outside_workspace"):
        assert by_name[name]["detector_flagged"] is True, name
        assert by_name[name]["detector_findings"], name


def test_report_is_json_serializable() -> None:
    report = run_security_benchmark()
    dumped = json.dumps(report)
    assert json.loads(dumped) == report
