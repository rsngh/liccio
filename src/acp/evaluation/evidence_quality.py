"""Evidence tiers + activation-aware solve-rate denominators (Round 25 feedback #2/#3).

Two pieces of measurement discipline the review demands:

1. **Evidence tier** — every report should declare how strong its evidence is, from
   ``synthetic`` (deterministic generator) up to ``production_shadow`` (observed on real
   work). A product claim is only as strong as its weakest cited tier.

2. **No hidden denominator** — a single "solve rate" is ambiguous. This module reports it
   over FOUR explicit denominators so a reader always knows what it rests on:
   - over_all: solved / every attempt (includes infra/no-op);
   - over_conclusive: solved / conclusive attempts (the measurement-trust denominator);
   - over_activated: solved / attempts where the harness actually did work (a no-op vendor
     return is excluded — the Alpha-25 self-catch);
   - over_trusted_activated: solved / activated-and-measurement-trusted attempts (strictest).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EvidenceTier(str, Enum):
    """Ordered weakest -> strongest. A report's tier is the weakest evidence it rests on."""
    SYNTHETIC = "synthetic"                     # deterministic generator, no model
    FIXTURE = "fixture"                         # canned repo, offline verification
    SEMI_LIVE = "semi_live"                     # some live calls, some stubbed
    LIVE_API = "live_api"                       # real OpenAI/Anthropic API rollouts
    VENDOR_NATIVE_LIVE = "vendor_native_live"   # real codex/claude/openhands CLI solves
    REAL_REPO_REPLAY = "real_repo_replay"       # real historical issue + known fix
    PRODUCTION_SHADOW = "production_shadow"      # observed on real production work


_TIER_ORDER = list(EvidenceTier)
TIER_RANK = {t: i for i, t in enumerate(_TIER_ORDER)}


def weakest_tier(tiers: list) -> EvidenceTier:
    """A composite claim is only as strong as its weakest evidence."""
    if not tiers:
        return EvidenceTier.SYNTHETIC
    return min((EvidenceTier(t) for t in tiers), key=lambda t: TIER_RANK[t])


@dataclass
class SolveRateBreakdown:
    n_all: int
    n_conclusive: int
    n_activated: int
    n_trusted_activated: int
    solve_rate_all: float
    solve_rate_conclusive: float
    solve_rate_activated: float
    solve_rate_trusted_activated: float

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def solve_rate_breakdown(cells: list, *, min_quality: float = 0.7) -> SolveRateBreakdown:
    """Compute the four-denominator solve-rate breakdown from attempt cells.

    Each cell is a dict/obj with: ``success`` (verified solve), an outcome/conclusive
    signal, an ``activated`` signal (the harness did work), and a ``measurement_quality``.
    Activation is inferred from ``activated`` / ``diff_captured`` / ``tool_calls`` / success
    so a no-op return is never counted as an activated attempt.
    """
    from acp.evaluation.measurement_hygiene import classify_attempt

    def g(c, k, default=None):
        return c.get(k, default) if isinstance(c, dict) else getattr(c, k, default)

    n_all = len(cells)
    solved_all = conclusive = solved_conc = activated = solved_act = 0
    trusted_act = solved_trusted = 0
    for c in cells:
        success = bool(g(c, "success", False) or g(c, "verification_pass", False))
        outcome = classify_attempt(c)
        is_conclusive = outcome.is_conclusive_quality
        act = bool(g(c, "activated", None) if g(c, "activated", None) is not None
                   else (g(c, "diff_captured", False) or (g(c, "tool_calls", 0) or 0) > 0
                         or success))
        mq = g(c, "measurement_quality", 1.0)
        mq = mq if isinstance(mq, (int, float)) else 1.0
        if success:
            solved_all += 1
        if is_conclusive:
            conclusive += 1
            if success:
                solved_conc += 1
        if act:
            activated += 1
            if success:
                solved_act += 1
            if mq >= min_quality and is_conclusive:
                trusted_act += 1
                if success:
                    solved_trusted += 1
    return SolveRateBreakdown(
        n_all=n_all, n_conclusive=conclusive, n_activated=activated,
        n_trusted_activated=trusted_act,
        solve_rate_all=_rate(solved_all, n_all),
        solve_rate_conclusive=_rate(solved_conc, conclusive),
        solve_rate_activated=_rate(solved_act, activated),
        solve_rate_trusted_activated=_rate(solved_trusted, trusted_act))


def stamp_evidence(report: dict, tier: EvidenceTier | str) -> dict:
    """Label a report with its evidence tier (string value), returning the same dict."""
    report["evidence_tier"] = EvidenceTier(tier).value
    return report
