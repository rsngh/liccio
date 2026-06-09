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
    model: str           # provider model id
    in_per_tok: float    # USD per input token
    out_per_tok: float   # USD per output token
    provider: str = "anthropic"   # anthropic | gemini

    def cost(self, in_tok: int, out_tok: int) -> float:
        return round((in_tok or 0) * self.in_per_tok + (out_tok or 0) * self.out_per_tok, 6)

    def adapter(self):
        """Return a fresh single-shot adapter for this tier's provider/model."""
        if self.provider == "gemini":
            from acp.agents.gemini_agent import GeminiAgentAdapter
            # pro is a thinking model -> needs a larger emit budget to leave room for code
            mt = 16384 if "pro" in self.model else 8192
            return GeminiAgentAdapter(name=self.name, model=self.model, max_output_tokens=mt)
        from acp.agents.claude_agent import ClaudeAgentAdapter
        return ClaudeAgentAdapter(name=self.name, model=self.model)


# Published per-1M blended pricing (USD).
# Anthropic: haiku $1/$5, sonnet $3/$15, opus $15/$75.
HAIKU = Tier("haiku", "claude-haiku-4-5", 1.0 / 1e6, 5.0 / 1e6)
SONNET = Tier("sonnet", "claude-sonnet-4-6", 3.0 / 1e6, 15.0 / 1e6)
OPUS = Tier("opus", "claude-opus-4-8", 15.0 / 1e6, 75.0 / 1e6)
# Google Gemini 3.x (genuinely DIFFERENT provider family). Prices for these preview models are
# ESTIMATES from the published flash-lite/flash/pro tiering (labelled as such in the report); the
# RELATIVE ordering flash_lite < flash < pro and "all cheaper than opus" is the load-bearing fact.
# gemini_flash_lite: no-thinking, cheapest/fastest tier
GEMINI_FLASH_LITE = Tier("gemini_flash_lite", "gemini-3.1-flash-lite",
                         0.10 / 1e6, 0.40 / 1e6, provider="gemini")
GEMINI_FLASH = Tier("gemini_flash", "gemini-3-flash-preview", 0.30 / 1e6, 2.50 / 1e6,
                    provider="gemini")
GEMINI_PRO = Tier("gemini_pro", "gemini-3.1-pro-preview", 2.0 / 1e6, 12.0 / 1e6, provider="gemini")

TIERS = {t.name: t for t in (HAIKU, SONNET, OPUS)}
ALL_TIERS = {t.name: t for t in
             (GEMINI_FLASH_LITE, GEMINI_FLASH, HAIKU, SONNET, GEMINI_PRO, OPUS)}

# Ratio facts for the report: opus output costs 15x haiku, 5x sonnet, ~30x flash, ~190x flash-lite.
OPUS_OVER_HAIKU = OPUS.out_per_tok / HAIKU.out_per_tok  # 15.0
OPUS_OVER_SONNET = OPUS.out_per_tok / SONNET.out_per_tok  # 5.0
OPUS_OVER_GEMINI_FLASH = OPUS.out_per_tok / GEMINI_FLASH.out_per_tok  # 30.0
OPUS_OVER_GEMINI_FLASH_LITE = OPUS.out_per_tok / GEMINI_FLASH_LITE.out_per_tok  # ~187.5
