"""Documentation consistency test (round-4 Block A / Additional tests §1).

Cheap structural invariants that catch the most common doc drift: the docs must
reflect Alpha-4 reality (two true harnesses), the Alpha-4 checklist must list
its required artifacts and they must exist, and no doc may still claim that only
one true harness exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text()


def test_two_true_harnesses_exist_in_code() -> None:
    from acp.agents import build_default_registry
    reg = build_default_registry()
    harnesses = [n for n in reg.names()
                 if getattr(reg.get(n), "is_harness", False)]
    assert {"openai_harness", "claude_harness"}.issubset(set(harnesses)), harnesses


def test_current_status_mentions_second_harness() -> None:
    status = _read("CURRENT_STATUS.md")
    assert "claude_harness" in status or "ClaudeHarnessAdapter" in status
    assert "openai_harness" in status or "OpenAIHarnessAdapter" in status


def test_no_doc_claims_single_harness() -> None:
    for name in ("CURRENT_STATUS.md", "FINAL_REPORT.md", "ALPHA4_CHECKLIST.md"):
        text = _read(name).lower()
        assert "only one true harness" not in text, name


def test_alpha4_checklist_lists_artifacts_and_they_exist() -> None:
    checklist = _read("ALPHA4_CHECKLIST.md")
    required = [
        "evals/reports/docker_security.json",
        "evals/reports/no_patch_bakeoff.json",
        "evals/reports/multi_harness_trace_bakeoff.json",
        "evals/reports/calibration.json",
    ]
    for art in required:
        assert art in checklist, f"{art} not referenced in ALPHA4_CHECKLIST.md"
        assert (ROOT / art).exists(), f"{art} missing on disk"


def test_history_archive_exists() -> None:
    assert (ROOT / "HISTORY.md").exists()


def test_alpha5_checklist_artifacts_exist() -> None:
    checklist = _read("ALPHA5_CHECKLIST.md")
    required = [
        "evals/reports/multi_harness_v2.json",
        "evals/reports/router_replay.json",
        "evals/reports/calibration_v2.json",
        "evals/reports/sandbox_redteam.json",
        "evals/reports/postmerge_sim.json",
        "reports/live/live_openai_claude_bakeoff.json",
    ]
    for art in required:
        assert art in checklist, f"{art} not referenced in ALPHA5_CHECKLIST.md"
        assert (ROOT / art).exists(), f"{art} missing on disk"


def test_alpha5_report_present() -> None:
    assert (ROOT / "ALPHA5_REPORT.md").exists()
    assert len(_read("ALPHA5_REPORT.md").strip()) > 200


@pytest.mark.parametrize("doc", ["CURRENT_STATUS.md", "FINAL_REPORT.md", "ALPHA4_CHECKLIST.md"])
def test_docs_present_and_nonempty(doc) -> None:
    assert len(_read(doc).strip()) > 200


def test_status_schema_defines_all_categories() -> None:
    schema = _read("docs/status_schema.md").lower()
    for cat in ("real local", "real service-backed", "acp true harness",
                "vendor harness", "simple model adapter", "fallback", "stub"):
        assert cat in schema, f"status_schema.md missing category {cat!r}"


def test_current_status_matches_committed_test_count() -> None:
    # the headline test count in CURRENT_STATUS must match reports/pytest.txt
    pytest_txt = _read("reports/pytest.txt")
    import re
    m = re.search(r"(\d+) passed", pytest_txt)
    assert m, "reports/pytest.txt has no 'N passed' line"
    passed = m.group(1)
    status = _read("CURRENT_STATUS.md")
    assert passed in status, (
        f"CURRENT_STATUS.md does not cite the committed pass count {passed}")


def test_alpha6_checklist_artifacts_exist() -> None:
    checklist = _read("ALPHA6_CHECKLIST.md")
    required = [
        "evals/reports/ope.json",
        "evals/reports/context_strategy_benchmark.json",
        "reports/live/alpha6_openai_experiment.json",
    ]
    for art in required:
        assert art in checklist, f"{art} not referenced in ALPHA6_CHECKLIST.md"
        assert (ROOT / art).exists(), f"{art} missing on disk"


def test_alpha6_report_present() -> None:
    assert (ROOT / "ALPHA6_REPORT.md").exists()
    assert len(_read("ALPHA6_REPORT.md").strip()) > 200


def test_alpha7_checklist_artifacts_exist() -> None:
    checklist = _read("ALPHA7_CHECKLIST.md")
    required = [
        "evals/reports/real_log_ope.json",
        "evals/reports/viability_matrix.json",
        "evals/reports/training_candidate_report.json",
        "evals/reports/vendor_harness_smoke.json",
        "evals/reports/context_downstream_benchmark.json",
        "reports/live/alpha7_openai_experiment.json",
    ]
    for art in required:
        assert art in checklist, f"{art} not referenced in ALPHA7_CHECKLIST.md"
        assert (ROOT / art).exists(), f"{art} missing on disk"


def test_alpha7_report_present() -> None:
    assert (ROOT / "ALPHA7_REPORT.md").exists()
    assert len(_read("ALPHA7_REPORT.md").strip()) > 200


def test_alpha8_checklist_artifacts_exist() -> None:
    checklist = _read("ALPHA8_CHECKLIST.md")
    required = [
        "evals/reports/artifact_manifest.json",
        "evals/reports/viability_learned_eval.json",
        "evals/reports/context_strategy_learned_eval.json",
        "evals/reports/evaluator_trust_model.json",
        "evals/reports/repair_classifier.json",
        "evals/reports/policy_canary_sim.json",
        "evals/reports/exploration_plan.json",
    ]
    for art in required:
        assert art in checklist, f"{art} not referenced in ALPHA8_CHECKLIST.md"
        assert (ROOT / art).exists(), f"{art} missing on disk"


def test_alpha8_report_present() -> None:
    assert (ROOT / "ALPHA8_REPORT.md").exists()
    assert len(_read("ALPHA8_REPORT.md").strip()) > 200


def test_artifact_manifest_all_valid() -> None:
    from acp.observability.artifact_manifest import build_manifest
    m = build_manifest(ROOT, generated_at="test")
    assert m.all_valid(), [a.path for a in m.invalid()]


def test_no_stale_single_harness_or_future_claims() -> None:
    # completed features must not be described as future work / not-implemented
    status = _read("CURRENT_STATUS.md").lower()
    for stale in ("only one true harness",
                  "not full tool-loop harnesses",
                  "are simple model adapters* (single json-edit prompt), not full"):
        assert stale not in status, f"stale claim in CURRENT_STATUS.md: {stale!r}"
