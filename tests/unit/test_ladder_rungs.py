"""P12 W3: the rung-subset resolver for the in-process complementarity A/B (no LLM, no I/O)."""

from __future__ import annotations

import pytest
from evals.issue_replay.ladder_live import RUNGS, _resolve_rungs


def test_default_is_full_ladder() -> None:
    assert _resolve_rungs(None, None) == RUNGS


def test_rungs_subset_preserves_requested_order() -> None:
    assert _resolve_rungs("inproc_repair2,inproc_sonnet", None) == (
        "inproc_repair2", "inproc_sonnet")
    assert _resolve_rungs(" inproc_sonnet ", None) == ("inproc_sonnet",)  # whitespace ok


def test_exclude_drops_from_default_keeping_order() -> None:
    assert _resolve_rungs(None, "inproc_sonnet") == (
        "inproc_repair2", "gemini_cli", "claude_code", "codex_cli")


def test_rungs_and_exclude_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="not both"):
        _resolve_rungs("inproc_repair2", "inproc_sonnet")


def test_unknown_rung_rejected() -> None:
    with pytest.raises(ValueError, match="unknown rung"):
        _resolve_rungs("inproc_repair2,gpt5_cli", None)
