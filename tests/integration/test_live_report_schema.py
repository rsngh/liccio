"""Live report redaction + committed-artifact schema (round-5 WS2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acp.observability.live_report import assert_no_secrets, redact_report

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "reports/live/live_openai_claude_bakeoff.json"

_FORBIDDEN_KEYS = {"prompt", "messages", "system", "unified_diff", "diff",
                   "session_id", "response_id", "api_key", "stdout"}
_REQUIRED_CELL_FIELDS = {"adapter", "task", "status", "success", "verification_pass",
                         "tool_calls", "changed_files", "tokens", "cost_usd", "latency_s"}


def test_redact_drops_sensitive_keys_and_keeps_metrics() -> None:
    raw = {
        "api_key": "sk-secret", "session_id": "sess_123", "unified_diff": "+x",
        "messages": [{"role": "user", "content": "secret prompt"}],
        "tool_calls": 3, "tokens": 1500, "total_tokens": 1500,
        "changed_files": ["/abs/path/calculator.py"],
        "cost_usd": 0.0015, "status": "succeeded",
    }
    red = redact_report(raw)
    assert red["api_key"] == "[REDACTED]"
    assert red["session_id"] == "[REDACTED]"
    assert red["unified_diff"] == "[REDACTED]"
    assert red["messages"] == "[REDACTED]"
    # metrics survive
    assert red["tool_calls"] == 3 and red["tokens"] == 1500 and red["total_tokens"] == 1500
    assert red["cost_usd"] == 0.0015 and red["status"] == "succeeded"
    # paths reduced to basenames
    assert red["changed_files"] == ["calculator.py"]


def test_assert_no_secrets_catches_leak(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak-value-xyz")
    with pytest.raises(AssertionError):
        assert_no_secrets({"oops": "sk-leak-value-xyz"})


@pytest.mark.skipif(not LIVE.exists(), reason="no committed live bakeoff artifact")
def test_committed_live_artifact_is_clean_and_complete() -> None:
    report = json.loads(LIVE.read_text())
    # both real harnesses present and solved the same task
    assert set(report["by_adapter"]) >= {"openai_harness", "claude_harness"}
    for adapter in ("openai_harness", "claude_harness"):
        assert report["by_adapter"][adapter]["solve_rate"] == 1.0
    # every cell has the required reviewable metrics
    for cell in report["cells"]:
        assert _REQUIRED_CELL_FIELDS.issubset(set(cell)), cell.keys()
    # no forbidden raw keys carry real (non-redacted) values anywhere
    def _walk(v):
        if isinstance(v, dict):
            for k, vv in v.items():
                if k.lower() in _FORBIDDEN_KEYS:
                    assert vv == "[REDACTED]", f"{k} not redacted: {vv!r}"
                _walk(vv)
        elif isinstance(v, list):
            for x in v:
                _walk(x)
    _walk(report)
    # changed files are basenames, not absolute paths
    for cell in report["cells"]:
        for f in cell["changed_files"]:
            assert "/" not in f, f"absolute path leaked: {f}"
