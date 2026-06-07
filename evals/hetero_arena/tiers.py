"""Model tiers + tier-aware pricing for the heterogeneity arena.

The metarouter's central economic claim — *use a cheap model, escalate to a strong one only when
needed* — is untestable with one model. These are the genuinely different Anthropic tiers that ARE
reachable here (haiku/sonnet/opus), each with its real published blended price so cost-per-verified
-success is attributed honestly per tier. Gemini is included as a hook but is network-unreachable in
this environment (documented, never claimed live).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    name: str            # short label used in reports
    model: str           # Anthropic model id
    in_per_tok: float    # USD per input token
    out_per_tok: float   # USD per output token

    def cost(self, in_tok: int, out_tok: int) -> float:
        return round((in_tok or 0) * self.in_per_tok + (out_tok or 0) * self.out_per_tok, 6)


# Published per-1M blended pricing (USD): haiku $1/$5, sonnet $3/$15, opus $15/$75.
HAIKU = Tier("haiku", "claude-haiku-4-5", 1.0 / 1_000_000, 5.0 / 1_000_000)
SONNET = Tier("sonnet", "claude-sonnet-4-6", 3.0 / 1_000_000, 15.0 / 1_000_000)
OPUS = Tier("opus", "claude-opus-4-8", 15.0 / 1_000_000, 75.0 / 1_000_000)

TIERS = {t.name: t for t in (HAIKU, SONNET, OPUS)}

# Ratio facts for the report: opus output costs 15x haiku output, 5x sonnet output.
OPUS_OVER_HAIKU = OPUS.out_per_tok / HAIKU.out_per_tok  # 15.0
OPUS_OVER_SONNET = OPUS.out_per_tok / SONNET.out_per_tok  # 5.0
