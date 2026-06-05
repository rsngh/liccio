"""Tool-use RL / format-adherence dataset export (Alpha 24 area 12).

Tool-N1 trains tool-use with BINARY rewards for functional correctness and format adherence
rather than supervised reasoning traces. ACP already measures HAR (harness activation),
HFR (harness following) and tool activation, so those become the reward signals here. This
module turns recorded tool calls into RL-ready examples with two binary rewards —
format_reward (the call was well-formed and parseable) and functional_reward (the call
achieved its intended effect) — plus a malformed-call detector and a secret-clean JSONL
export. It is dataset preparation only: no RL backend is required to run it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_SECRET = re.compile(r"sk-[A-Za-z0-9]{20,}|ANTHROPIC_API_KEY|OPENAI_API_KEY")


@dataclass
class ToolCallRecord:
    adapter: str
    tool_name: str
    args: dict = field(default_factory=dict)
    well_formed: bool = True            # parsed against the tool schema
    functional_success: bool = False    # the call achieved its effect (e.g. file written)
    raw: str = ""                       # raw model output (for format auditing)


def format_reward(r: ToolCallRecord) -> int:
    """1 iff the tool call was well-formed (schema-valid, parseable, named)."""
    return int(bool(r.well_formed and r.tool_name))


def functional_reward(r: ToolCallRecord) -> int:
    """1 iff the (well-formed) call achieved its intended effect."""
    return int(bool(r.well_formed and r.functional_success))


def _secret_clean(text: str) -> bool:
    return not _SECRET.search(text or "")


@dataclass
class ToolFormatDataset:
    examples: list = field(default_factory=list)   # list[dict]
    n_malformed: int = 0
    malformed_rate: float = 0.0
    secret_clean: bool = True
    by_adapter: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"experiment": "tool_format_dataset", "n_examples": len(self.examples),
                "n_malformed": self.n_malformed, "malformed_rate": self.malformed_rate,
                "secret_clean": self.secret_clean, "by_adapter": self.by_adapter}

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(e, sort_keys=True) for e in self.examples)


def build_tool_format_dataset(records: list[ToolCallRecord]) -> ToolFormatDataset:
    """Build the RL-ready dataset with binary rewards + a malformed-rate audit."""
    examples: list[dict] = []
    by_adapter: dict[str, dict] = {}
    n_malformed = 0
    secret_clean = True
    for r in records:
        fmt, fn = format_reward(r), functional_reward(r)
        if not r.well_formed:
            n_malformed += 1
        if not (_secret_clean(r.raw) and _secret_clean(json.dumps(r.args))):
            secret_clean = False
            continue                    # never export a secret-bearing example
        examples.append({
            "adapter": r.adapter, "tool_name": r.tool_name, "args": r.args,
            "format_reward": fmt, "functional_reward": fn,
            # combined reward (Tool-N1 style): must be well-formed AND effective
            "reward": int(fmt and fn)})
        a = by_adapter.setdefault(r.adapter, {"n": 0, "malformed": 0, "functional": 0})
        a["n"] += 1
        a["malformed"] += int(not r.well_formed)
        a["functional"] += fn
    n = len(records)
    return ToolFormatDataset(
        examples=examples, n_malformed=n_malformed,
        malformed_rate=round(n_malformed / n, 4) if n else 0.0,
        secret_clean=secret_clean, by_adapter=by_adapter)


def harness_activation_summary(records: list[ToolCallRecord]) -> dict:
    """HAR/HFR-style activation signals per adapter for the training/eval export."""
    out: dict[str, dict] = {}
    for r in records:
        a = out.setdefault(r.adapter, {"calls": 0, "well_formed": 0, "functional": 0})
        a["calls"] += 1
        a["well_formed"] += int(r.well_formed)
        a["functional"] += int(r.functional_success)
    for a in out.values():
        c = a["calls"] or 1
        a["har"] = round(a["well_formed"] / c, 4)        # activation: well-formed share
        a["hfr"] = round(a["functional"] / c, 4)         # following: functional share
    return out
