# ruff: noqa: E501
"""Heterogeneity-arena policies — the real economic test of a metarouter.

With three genuinely different tiers reachable (haiku/sonnet/opus), we can finally test the core
claim the metarouter exists for: *use a cheap model, escalate to a strong one only when needed, and
match the strong model's verified success at a fraction of its cost.* All policies are single-shot
per call (no hidden-test leakage); the only production-available proceed signal is the PUBLIC test,
so escalation/selection use that and we REPORT the held-out hidden verdict.

Policies:
  * ``{haiku,sonnet,opus}_single``      — fixed-tier single-shot (floor / mid / ceiling).
  * ``cost_aware_escalation``           — haiku->sonnet->opus, stop as soon as the public test
                                          passes (the real router); reports cost actually spent.
  * ``best_of_k_haiku``                 — sample k haiku candidates, select by public-test signal
                                          (weak-model critic-comparator); does cheap k rival a
                                          strong single model per dollar?
  * ``escalate_on_abstain``             — sufficiency-gated escalation: only spend the strong tier
                                          when a cheap pre-check says the cheap attempt is unsound.
"""

from __future__ import annotations

import time

from evals.hetero_arena.tiers import HAIKU, OPUS, SONNET
from evals.metarouter_arena.policies import _single_shot
from evals.metarouter_arena.schema import AdapterStatus, ArenaAttempt, ArenaTaskSpec

from acp.agents.claude_agent import ClaudeAgentAdapter

# one adapter per tier, reused across tasks (stateless single-shot)
_ADAPTERS = {t.name: ClaudeAgentAdapter(name=t.name, model=t.model) for t in (HAIKU, SONNET, OPUS)}
_TIER = {"haiku": HAIKU, "sonnet": SONNET, "opus": OPUS}

# pure model-tier ladder (minimal context throughout): isolates the MODEL-strength lever.
TIER_LADDER = (("haiku", "minimal"), ("sonnet", "minimal"), ("opus", "minimal"))
# economically-correct ladder: escalate CONTEXT on the cheap model first, only THEN pay for a
# bigger model — fixing context is far cheaper than upgrading the tier.
CONTEXT_FIRST_LADDER = (("haiku", "minimal"), ("haiku", "repo_map"),
                        ("sonnet", "repo_map"), ("opus", "repo_map"))


def _fixed_tier(tier_name: str):
    def _policy(spec: ArenaTaskSpec, root, **_) -> ArenaAttempt:
        tier = _TIER[tier_name]
        att = _single_shot(_ADAPTERS[tier_name], spec, root, strategy="minimal",
                           policy_name=f"{tier_name}_single", cost_fn=tier.cost)
        att.policy = f"{tier_name}_single"
        return att
    return _policy


policy_haiku_single = _fixed_tier("haiku")
policy_sonnet_single = _fixed_tier("sonnet")
policy_opus_single = _fixed_tier("opus")


def _escalate(spec: ArenaTaskSpec, root, ladder, policy_name: str) -> ArenaAttempt:
    """Walk an escalation ladder of (tier, context-strategy) rungs; stop the moment the PUBLIC
    test passes. Report the held-out hidden verdict of the stopping (or last) rung. Cost is the
    sum of every rung actually invoked — so easy tasks pay cheap-rung money and only genuinely
    hard ones pay for context + a bigger model.
    """
    t0 = time.time()
    total_cost = 0.0
    rung_path: list[str] = []
    last = None
    for tier_name, strategy in ladder:
        tier = _TIER[tier_name]
        att = _single_shot(_ADAPTERS[tier_name], spec, root, strategy=strategy,
                           policy_name=f"{policy_name}_{tier_name}_{strategy}", cost_fn=tier.cost)
        total_cost += att.cost_usd
        rung_path.append(f"{tier_name}:{strategy}")
        last = att
        if not att.conclusive:
            continue  # infra noise on this rung -> try next (don't charge a false verdict)
        if att.public_solved:
            break     # public test passes -> the router stops here (the production stop signal)
    assert last is not None
    return ArenaAttempt(
        task=spec.name, policy=policy_name,
        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value if last.conclusive else AdapterStatus.LIVE_INCONCLUSIVE.value,
        solved=last.solved, public_solved=last.public_solved, conclusive=last.conclusive,
        cost_usd=round(total_cost, 6), latency_s=round(time.time() - t0, 2),
        changed_files=last.changed_files, candidates_sampled=len(rung_path),
        detail="->".join(rung_path))


def policy_cost_aware_escalation(spec: ArenaTaskSpec, root, **_) -> ArenaAttempt:
    """Pure model-tier escalation (haiku->sonnet->opus, minimal context): does paying for a
    stronger model rescue tasks the cheap model fails? Isolates the model-strength lever."""
    return _escalate(spec, root, TIER_LADDER, "cost_aware_escalation")


def policy_context_first_escalation(spec: ArenaTaskSpec, root, **_) -> ArenaAttempt:
    """Economically-correct ladder: add CONTEXT on the cheap model before upgrading the tier
    (haiku-minimal -> haiku-repo_map -> sonnet -> opus). Tests whether the cheapest fix (better
    context, same cheap model) rescues failures before any tier upgrade is paid for."""
    return _escalate(spec, root, CONTEXT_FIRST_LADDER, "context_first_escalation")


def policy_best_of_k_haiku(spec: ArenaTaskSpec, root, *, k: int = 3, **_) -> ArenaAttempt:
    """Sample k cheap (haiku) candidates; select by the public-test proof signal; report hidden.

    The weak-model critic-comparator thesis: can a cheap model, sampled k times and selected by an
    execution signal, rival a strong single model per dollar? Cost = k haiku calls.
    """
    t0 = time.time()
    cands = [_single_shot(_ADAPTERS["haiku"], spec, root, strategy="minimal",
                          policy_name=f"bok_haiku_{i}", cost_fn=HAIKU.cost) for i in range(k)]
    cost = round(sum(c.cost_usd for c in cands), 6)
    conclusive = any(c.conclusive for c in cands)
    # comparator: prefer a candidate whose PUBLIC test passes; else first conclusive; else first
    chosen = next((c for c in cands if c.public_solved),
                  next((c for c in cands if c.conclusive), cands[0]))
    return ArenaAttempt(
        task=spec.name, policy="best_of_k_haiku",
        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value if conclusive else AdapterStatus.LIVE_INCONCLUSIVE.value,
        solved=chosen.solved, public_solved=chosen.public_solved, conclusive=conclusive,
        cost_usd=cost, latency_s=round(time.time() - t0, 2), candidates_sampled=k,
        changed_files=chosen.changed_files, detail=f"best-of-{k} haiku by public proof")


ALL_POLICIES = {
    "haiku_single": policy_haiku_single,
    "sonnet_single": policy_sonnet_single,
    "opus_single": policy_opus_single,
    "cost_aware_escalation": policy_cost_aware_escalation,
    "context_first_escalation": policy_context_first_escalation,
    "best_of_k_haiku": policy_best_of_k_haiku,
}
