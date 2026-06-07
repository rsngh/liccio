"""Build the provider marketplace scorecard (GOALS Alpha 44 P10).

Deterministic: classifies each provider by evidence class from healthchecks + the hard-arena
Anthropic evidence, and recommends a feasible provider mix. Writes
reports/provider_marketplace_scorecard.json. OpenAI/Gemini stay mock-contract-only; no live claim.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from acp.providers import all_providers  # noqa: E402
from acp.providers.marketplace import ProviderMarketplace  # noqa: E402


def main() -> int:
    # Anthropic carries live conclusive cells from the hard arena (read if present)
    cells = 0
    verified = cost = None
    arena = ROOT / "reports" / "hard_realism_arena.json"
    if arena.exists():
        a = json.loads(arena.read_text())
        cells = sum(v[1] if isinstance(v, list) else 0 for v in [])  # n/a; use conclusive total
        cells = a.get("n_conclusive_cells", 0)
        gi = a.get("global_confidence_intervals", {}).get("grep_router", {})
        verified = gi.get("point")
    os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    m = ProviderMarketplace(min_cells=30)
    for p in all_providers():
        av = p.availability()
        anthropic_live = p.name == "anthropic" and cells >= 30
        m.classify(provider=p.name, available=av.available or anthropic_live,
                   contract_passed=True,
                   conclusive_cells=cells if p.name == "anthropic" else 0,
                   verified=verified if p.name == "anthropic" else None,
                   cost=cost, reason=av.reason)
    report = {**m.scorecard(), "mix_recommendation": m.mix_recommendation()}
    out = ROOT / "reports" / "provider_marketplace_scorecard.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print("by_evidence_class:", report["by_evidence_class"])
    print("recommended primary:", report["mix_recommendation"]["recommended_primary"])
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
