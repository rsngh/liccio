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


@pytest.mark.parametrize("doc", ["CURRENT_STATUS.md", "FINAL_REPORT.md", "ALPHA4_CHECKLIST.md"])
def test_docs_present_and_nonempty(doc) -> None:
    assert len(_read(doc).strip()) > 200
