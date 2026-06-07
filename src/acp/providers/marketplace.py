"""Provider marketplace + scorecard (GOALS Alpha 44 P10).

Models providers as a marketplace WITHOUT needing live OpenAI/Gemini. A scorecard separates each
provider by evidence class — live_conclusive / replay_imported / mock_contract_only / unavailable
— so Anthropic live evidence can drive local policy while OpenAI/Gemini remain hooks. The mix
optimizer only ever recommends a FEASIBLE provider (available + contract-passed + uncontaminated +
enough conclusive cells); it never ranks an unavailable provider as a failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

EVIDENCE_CLASSES = ("live_conclusive", "replay_imported", "mock_contract_only", "unavailable")


@dataclass
class ProviderScorecardRow:
    provider: str
    evidence_class: str
    available: bool
    contract_passed: bool
    conclusive_cells: int = 0
    verified_success_rate: float | None = None
    cost_per_verified_success: float | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {"provider": self.provider, "evidence_class": self.evidence_class,
                "available": self.available, "contract_passed": self.contract_passed,
                "conclusive_cells": self.conclusive_cells,
                "verified_success_rate": self.verified_success_rate,
                "cost_per_verified_success": self.cost_per_verified_success, "reason": self.reason}


@dataclass
class ProviderMarketplace:
    min_cells: int = 30
    rows: list[ProviderScorecardRow] = field(default_factory=list)

    def classify(self, *, provider: str, available: bool, contract_passed: bool,
                 conclusive_cells: int = 0, verified: float | None = None,
                 cost: float | None = None, reason: str = "",
                 has_replay: bool = False) -> ProviderScorecardRow:
        if available and conclusive_cells >= self.min_cells:
            ec = "live_conclusive"
        elif has_replay:
            ec = "replay_imported"
        elif contract_passed and not available:
            ec = "mock_contract_only"
        else:
            ec = "unavailable"
        row = ProviderScorecardRow(provider, ec, available, contract_passed, conclusive_cells,
                                   verified, cost, reason)
        self.rows.append(row)
        return row

    def scorecard(self) -> dict:
        by_class: dict[str, list[str]] = {c: [] for c in EVIDENCE_CLASSES}
        for r in self.rows:
            by_class[r.evidence_class].append(r.provider)
        return {"experiment": "provider_marketplace_scorecard",
                "by_evidence_class": by_class,
                "rows": [r.to_dict() for r in self.rows]}

    def mix_recommendation(self) -> dict:
        """Recommend a provider mix only over FEASIBLE (live_conclusive) providers."""
        feasible = [r for r in self.rows if r.evidence_class == "live_conclusive"
                    and r.contract_passed]
        ranked = sorted(
            feasible,
            key=lambda r: ((r.verified_success_rate or 0.0) / (r.cost_per_verified_success or 1e9)),
            reverse=True)
        not_ranked = {r.provider: r.reason or f"evidence_class={r.evidence_class}"
                      for r in self.rows if r not in feasible}
        return {"recommended_primary": ranked[0].provider if ranked else None,
                "feasible_providers": [r.provider for r in ranked],
                "not_ranked": not_ranked,
                "note": "OpenAI/Gemini pluggable later via replay import; no live claim here"}
