"""Tests for the data-governance red-team lab (Alpha 11 WS11)."""

from __future__ import annotations

import json

from acp.evaluation.data_governance_redteam import run_data_governance_redteam


def test_every_attack_blocked_or_flagged() -> None:
    report = run_data_governance_redteam()
    attacks = report["attacks"]
    assert attacks, "expected at least one attack"
    for name, result in attacks.items():
        assert result["status"] in {"blocked", "flagged"}, (name, result)
        assert result["detail"]


def test_summary_all_blocked_no_leaks() -> None:
    report = run_data_governance_redteam()
    summary = report["summary"]
    assert summary["n_attacks"] == len(report["attacks"])
    assert summary["all_blocked"] is True
    assert summary["leaks"] == []


def test_expected_attack_classes_present() -> None:
    report = run_data_governance_redteam()
    names = set(report["attacks"])
    expected = {
        "private_repo_into_global_training",
        "repo_a_examples_in_repo_b_model",
        "memorization_canary_in_training",
        "allowlist_bypass",
        "model_artifact_without_rollback_plan",
        "dataset_export_before_leakage_audit",
    }
    assert expected <= names


def test_report_json_serializable() -> None:
    report = run_data_governance_redteam()
    assert json.loads(json.dumps(report)) == report
