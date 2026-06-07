"""Best-of-k v2 — diversity + strong proof-based comparator (GOALS Alpha 43 P3).

Weak proposals expose correct solutions only if (a) they are DIVERSE and (b) selection uses a
strong local soundness signal, not model self-ranking. This comparator rejects candidates that
pass public but fail hidden tests, touch forbidden files, sprawl (non-minimal diffs), or look
like test-gaming — then selects the minimal verified candidate. Deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# candidate diversity strategies (how the k candidates are generated)
DIVERSITY_STRATEGIES = (
    "same_model_different_context", "same_model_different_prompt", "repo_map_vs_grep_context",
    "cheap_model_then_strong_repair", "test_first_candidate", "minimal_patch_candidate",
    "security_hardened_candidate",
)


@dataclass
class Candidate:
    id: str
    public_pass: bool
    hidden_pass: bool
    diff_lines: int
    forbidden_file_touched: bool = False
    test_gaming_suspected: bool = False     # e.g. weakened/deleted tests
    strategy: str = "same_model_different_prompt"
    cost: float = 0.0
    proxy_pass: bool | None = None          # independent-proof verdict (online; not the oracle)


@dataclass
class ComparatorResult:
    selected: str | None
    selected_verified: bool
    n_candidates: int
    n_rejected: int
    reject_reasons: dict[str, str] = field(default_factory=dict)
    waste_rate: float = 0.0
    diversity: float = 0.0


def _eligible(c: Candidate) -> tuple[bool, str]:
    if c.forbidden_file_touched:
        return False, "forbidden_file_touched"
    if c.test_gaming_suspected:
        return False, "test_gaming_suspected"
    if c.public_pass and not c.hidden_pass:
        return False, "public_pass_hidden_fail"     # the classic over-fit-to-public reject
    return True, "ok"


def select_best(candidates: list[Candidate]) -> ComparatorResult:
    """Select the minimal-diff HIDDEN-verified candidate; reject gamed/forbidden/over-fit ones."""
    reject: dict[str, str] = {}
    eligible: list[Candidate] = []
    for c in candidates:
        ok, reason = _eligible(c)
        if ok:
            eligible.append(c)
        else:
            reject[c.id] = reason
    verified = [c for c in eligible if c.hidden_pass]
    chosen = min(verified, key=lambda c: (c.diff_lines, c.id)) if verified else None
    n = len(candidates)
    distinct = len({(c.strategy, c.diff_lines, c.hidden_pass) for c in candidates})
    used = 1 if chosen else 0
    return ComparatorResult(
        selected=chosen.id if chosen else None,
        selected_verified=chosen is not None,
        n_candidates=n, n_rejected=len(reject), reject_reasons=reject,
        waste_rate=round((n - used) / n, 4) if n else 0.0,
        diversity=round(distinct / n, 4) if n else 0.0)


def _eligible_online(c: Candidate) -> tuple[bool, str]:
    """Eligibility using the PROXY verdict (independent_proof) instead of the oracle hidden test."""
    if c.forbidden_file_touched:
        return False, "forbidden_file_touched"
    if c.test_gaming_suspected:
        return False, "test_gaming_suspected"
    if c.public_pass and c.proxy_pass is False:
        return False, "public_pass_proxy_fail"      # the over-fit reject, caught WITHOUT the oracle
    return True, "ok"


def select_best_online(candidates: list[Candidate]) -> ComparatorResult:
    """Online selection: pick the minimal-diff PROXY-verified candidate (no held-out test used).

    Degrades safely: if no candidate is proxy-verified, fall back to the first public-passing one
    (i.e. never worse than the public-only baseline). The realized correctness of the choice is
    measured by the caller against the true hidden oracle.
    """
    reject: dict[str, str] = {}
    eligible: list[Candidate] = []
    for c in candidates:
        ok, reason = _eligible_online(c)
        if ok:
            eligible.append(c)
        else:
            reject[c.id] = reason
    verified = [c for c in eligible if c.proxy_pass]
    if verified:
        chosen: Candidate | None = min(verified, key=lambda c: (c.diff_lines, c.id))
    else:
        chosen = next((c for c in candidates if c.public_pass),
                      candidates[0] if candidates else None)
    n = len(candidates)
    distinct = len({(c.strategy, c.diff_lines, c.proxy_pass) for c in candidates})
    used = 1 if chosen else 0
    return ComparatorResult(
        selected=chosen.id if chosen else None,
        selected_verified=bool(chosen and chosen.proxy_pass),
        n_candidates=n, n_rejected=len(reject), reject_reasons=reject,
        waste_rate=round((n - used) / n, 4) if n else 0.0,
        diversity=round(distinct / n, 4) if n else 0.0)


def early_stop_savings(candidates: list[Candidate]) -> dict:
    """If the first candidate is already hidden-verified, the rest are avoidable cost."""
    if candidates and candidates[0].hidden_pass and _eligible(candidates[0])[0]:
        saved = sum(c.cost for c in candidates[1:])
        return {"early_stopped": True, "candidates_avoided": len(candidates) - 1,
                "cost_saved": round(saved, 6)}
    return {"early_stopped": False, "candidates_avoided": 0, "cost_saved": 0.0}
