"""HuggingFace SFT JSONL exporter (Alpha-7 WS4).

Emits one ``{"prompt": ..., "completion": ...}`` object per
:class:`TrainingExample`. A final :class:`~acp.core.redaction.Redactor` pass
asserts no secret shape survives in the written output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from acp.core.redaction import DEFAULT_VALUE_PATTERNS, Redactor
from acp.schemas.training import TrainingExample


def _assert_clean(line: str) -> None:
    for pattern in DEFAULT_VALUE_PATTERNS:
        if re.search(pattern, line):
            raise AssertionError("secret-shaped token found in exported JSONL")


def export_hf_sft_jsonl(
    examples: list[TrainingExample], path: str | Path
) -> int:
    """Write ``examples`` as HF SFT prompt/completion JSONL; return count."""
    redactor = Redactor()
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for ex in examples:
            prompt = (
                f"[{ex.dataset_kind}] "
                + json.dumps(redactor.redact(ex.inputs), sort_keys=True)
            )
            completion = json.dumps(redactor.redact(ex.target), sort_keys=True)
            record = {"prompt": prompt, "completion": completion}
            line = json.dumps(record, ensure_ascii=False)
            _assert_clean(line)
            fh.write(line + "\n")
            count += 1
    return count
