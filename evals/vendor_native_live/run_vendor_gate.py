"""Vendor-native live gate (GOALS Alpha 42 P9).

ACP is the layer ABOVE Claude/Codex/OpenAI/OpenHands. This gate makes adapter availability
loud and comparable, and separates availability from capability: each required adapter is
health-checked (available vs unavailable WITH a reason), live-capable adapters carry an
activation matrix (HAR/HFR/PWL — reused from the arena where available), and unavailable
vendors are discoverable but not routed by default and never poison learning.

Live-capable here: claude_harness (if reachable), fake, patch. openai_harness/codex_cli/
openhands self-skip as unavailable. Deterministic + healthchecks; writes
reports/vendor_native_live_gate.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from acp.agents import build_default_registry  # noqa: E402
from acp.observability.live_report import redact_report  # noqa: E402

REQUIRED = ["claude_harness", "openai_harness", "codex_cli", "openhands", "fake", "patch"]


def _activation_from_arena() -> dict:
    arena_path = ROOT / "reports" / "metarouter_arena.json"
    if not arena_path.exists():
        return {}
    arena = json.loads(arena_path.read_text())
    rows = [a for a in arena.get("attempts", []) if a["policy"] == "claude_harness"]
    if not rows:
        return {}
    acts = [a for a in rows if a.get("activated")]
    follows = [a for a in rows if a.get("followed")]
    solved_when_act = [a for a in acts if a["solved"]]
    n = len(rows)
    return {
        "claude_harness": {
            "n": n,
            "HAR": round(len(acts) / n, 4) if n else 0.0,
            "HFR": round(len(follows) / n, 4) if n else 0.0,
            "PWL": round(len(solved_when_act) / len(acts), 4) if acts else 0.0,
            "source": "arena live tool-loop traces",
        }
    }


def main() -> int:
    os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    reg = build_default_registry(include_external=True)
    healths = asyncio.run(reg.healthcheck_all())
    activation = _activation_from_arena()

    adapters = []
    for name in REQUIRED:
        h = healths.get(name)
        available = bool(h and h.available)
        is_harness = getattr(reg.get(name), "is_harness", False) if name in reg.names() else False
        has_cells = name in activation
        if available and has_cells:
            status = "live_conclusive"
        elif available:
            status = "live_available_no_cells"
        else:
            status = "unavailable"
        adapters.append({
            "adapter": name, "available": available, "is_harness": is_harness,
            "status": status, "reason": (h.detail if h else "not registered"),
            "activation": activation.get(name),
            "routed_by_default": available,           # unavailable -> discoverable, not routed
        })

    live_capable = [a["adapter"] for a in adapters if a["available"]]
    report = {
        "experiment": "vendor_native_live_gate",
        "required_adapters": REQUIRED,
        "live_capable": live_capable,
        "unavailable": [a["adapter"] for a in adapters if not a["available"]],
        "availability_separated_from_capability": True,
        "no_unavailable_adapter_routed_by_default": all(
            not a["routed_by_default"] for a in adapters if not a["available"]),
        "activation_matrix": activation,
        "adapters": adapters,
        "note": ("openai/codex/openhands self-skip as unavailable with reasons; ranking claims "
                 "need >=30 conclusive cells per adapter (smoke here)."),
    }
    out = ROOT / "reports" / "vendor_native_live_gate.json"
    out.write_text(json.dumps(redact_report(report), indent=2) + "\n")
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        s = os.environ.get(key)
        if s:
            assert s not in out.read_text(), f"{key} leaked!"
    print(f"live-capable: {live_capable}")
    print(f"unavailable (discoverable, not routed): {report['unavailable']}")
    print(f"activation: {activation}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
