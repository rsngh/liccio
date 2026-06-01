"""Redaction for committed live-run artifacts (round-5 WS2).

Live harness runs touch a real provider; their raw traces contain things that
must never be committed: secrets, raw prompts/messages, full file contents,
command stdout, unified diffs, and provider response/session IDs. ``redact_report``
produces a *reviewable* artifact — counts, changed-file basenames, tokens, cost,
latency, verification status — with everything sensitive dropped or masked.

A live report is then safe to commit so reviewers can confirm "both harnesses
solved the same no-patch task" without exposing prompts or secrets.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from acp.core.redaction import Redactor

# Keys whose VALUES are dropped entirely (free text / raw payloads / ids).
_DROP_KEYS = {
    "prompt", "prompts", "messages", "content", "system", "raw", "response",
    "response_id", "request_id", "session_id", "stdout", "stderr",
    "unified_diff", "diff", "body", "result_summary", "arguments", "api_key",
    "openai_api_key", "anthropic_api_key",
}
# Keys whose list-of-paths values are reduced to basenames (no absolute paths).
_BASENAME_KEYS = {"file_writes", "file_reads_list", "changed_files", "files_written"}
# Numeric metric keys that LOOK sensitive (match TOKEN/KEY patterns) but are just
# counts — kept so the artifact stays reviewable.
_METRIC_ALLOW = {"tokens", "total_tokens", "input_tokens", "output_tokens"}

_redactor = Redactor()


def _basename_list(value: Any) -> Any:
    if isinstance(value, list):
        return [Path(str(v)).name for v in value]
    return value


def redact_report(value: Any) -> Any:
    """Recursively redact a report for safe committing."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            lk = k.lower()
            if lk in _METRIC_ALLOW:
                out[k] = redact_report(v)
            elif lk in _DROP_KEYS or _redactor.key_is_sensitive(k):
                out[k] = "[REDACTED]"
            elif lk in _BASENAME_KEYS:
                out[k] = _basename_list(v)
            else:
                out[k] = redact_report(v)
        return out
    if isinstance(value, list):
        return [redact_report(v) for v in value]
    if isinstance(value, str):
        return _redactor.redact_text(value)
    return value


def assert_no_secrets(report: Any) -> None:
    """Raise if a live key value appears anywhere in the (already redacted) blob."""
    import json

    blob = json.dumps(report)
    for env in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(env)
        if secret and secret in blob:
            raise AssertionError(f"redacted report still contains {env} value")
