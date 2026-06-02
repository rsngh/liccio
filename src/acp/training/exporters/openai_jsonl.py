"""OpenAI chat-format JSONL exporter (Alpha-7 WS4).

Emits one ``{"messages": [...]}`` object per :class:`TrainingExample`. The
system message names the dataset kind; the user message carries the (already
redacted) inputs; the assistant message carries the target. A final
:class:`~acp.core.redaction.Redactor` pass asserts no secret shape survives in
the written output.
"""

from __future__ import annotations

import json
from pathlib import Path

from acp.core.redaction import DEFAULT_VALUE_PATTERNS, Redactor
from acp.schemas.training import TrainingExample

_SYSTEM = "You are an ACP policy model. Dataset kind: {kind}."


def _assert_clean(line: str) -> None:
    import re

    for pattern in DEFAULT_VALUE_PATTERNS:
        if re.search(pattern, line):
            raise AssertionError("secret-shaped token found in exported JSONL")


def export_openai_jsonl(
    examples: list[TrainingExample], path: str | Path
) -> int:
    """Write ``examples`` as OpenAI chat JSONL; return the number written."""
    redactor = Redactor()
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for ex in examples:
            record = {
                "messages": [
                    {"role": "system", "content": _SYSTEM.format(kind=ex.dataset_kind)},
                    {
                        "role": "user",
                        "content": json.dumps(redactor.redact(ex.inputs), sort_keys=True),
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(redactor.redact(ex.target), sort_keys=True),
                    },
                ]
            }
            line = json.dumps(record, ensure_ascii=False)
            _assert_clean(line)
            fh.write(line + "\n")
            count += 1
    return count
