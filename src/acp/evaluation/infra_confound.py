"""Timeout-confound detector (Alpha 23 WS8).

A measurement-trust guard surfaced by the live graded benchmark: claude_code scored 0.667
at a 180s per-task cap but 1.0 at 240s. The "capability gap" was really TIMEOUT PRESSURE
(the hard `roman` task ran ~158s under the 180s cap), not a real capability difference.

Attributing a budget-induced shortfall to capability would corrupt routing and skill
evaluation. This module compares solve rates measured at two timeout budgets and flags the
gap as *infra-confounded* when it closes (or shrinks materially) as the budget is relaxed —
in which case the lower-budget shortfall must be treated as infra/inconclusive, exactly as
the measurement-trust layer treats a timeout.
"""

from __future__ import annotations

from dataclasses import dataclass

# A capability gap that closes by at least this much when the budget is relaxed is
# attributed to infra (timeout pressure), not capability.
CONFOUND_CLOSE_FRACTION = 0.5


@dataclass
class TimeoutConfoundVerdict:
    low_timeout_s: int
    high_timeout_s: int
    low_solve_rate: float
    high_solve_rate: float
    gap: float                 # high - low (>0 means relaxing the budget helped)
    confounded: bool
    recommendation: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def detect_timeout_confound(low_timeout_s: int, low_solve_rate: float,
                            high_timeout_s: int, high_solve_rate: float,
                            *, min_gap: float = 0.1) -> TimeoutConfoundVerdict:
    """Decide whether a solve-rate gap across two timeout budgets is infra-confounded.

    ``low_*`` is the tighter budget, ``high_*`` the more generous one. The gap is
    infra-confounded when (a) the tighter budget is genuinely tighter, (b) the gap is at
    least ``min_gap``, and (c) the more generous budget reaches near-ceiling — i.e. the
    shortfall is explained by time pressure rather than capability.
    """
    if high_timeout_s <= low_timeout_s:
        raise ValueError("high_timeout_s must exceed low_timeout_s")
    gap = round(high_solve_rate - low_solve_rate, 4)
    confounded = bool(
        gap >= min_gap
        and high_solve_rate >= low_solve_rate + CONFOUND_CLOSE_FRACTION * (1.0 - low_solve_rate)
    )
    if confounded:
        rec = (f"infra-confounded: the {low_solve_rate:.0%}->{high_solve_rate:.0%} gap closes "
               f"when the per-task budget is raised {low_timeout_s}->{high_timeout_s}s; treat "
               f"the {low_timeout_s}s shortfall as infra/inconclusive, not capability.")
    elif gap < min_gap:
        rec = ("stable: solve rate is budget-insensitive across these timeouts; the result "
               "reflects capability.")
    else:
        rec = (f"partial: relaxing the budget helped ({gap:+.2f}) but did not reach ceiling; "
               "a real capability component remains — re-measure with a fair budget.")
    return TimeoutConfoundVerdict(
        low_timeout_s=low_timeout_s, high_timeout_s=high_timeout_s,
        low_solve_rate=round(low_solve_rate, 4), high_solve_rate=round(high_solve_rate, 4),
        gap=gap, confounded=confounded, recommendation=rec)
