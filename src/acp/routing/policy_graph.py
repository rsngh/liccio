"""Coordination policy graph v2 (Alpha 33 — AgensFlow-style).

AgensFlow's thesis: the learned artifact is not a fixed pipeline but an AUDITABLE POLICY over
folded task signatures and coordination actions (invoke/skip:X/advisor/best-of-k/verify/
abstain). This module makes that explicit:

- ``FoldedTaskSignature`` folds the high-dimensional task context (regime, risk, ambiguity,
  evidence, reliability, measurement trust, evidence tier) into a compact discrete key, so
  similar situations share evidence.
- ``PolicyGraph`` maps signature -> per-action value learned ONLY from conclusive,
  measurement-trusted rewards (the hard invariant), with a global fallback for unseen
  signatures and ``warm_start`` to transfer values across repos/task families.
- ``skip_policy`` decides skip:planner/retrieval/reviewer by signature, but NEVER skips
  strict verification on high-risk/security.
- ``reward_audit`` lets a cross-judge reward check flip a promotion decision.

Every value carries its sample count so a thin-evidence action is never trusted blindly.
"""

from __future__ import annotations

from dataclasses import dataclass

ACTIONS = ("invoke", "skip:planner", "skip:retrieval", "skip:reviewer", "consult_advisor",
           "best_of_k", "run_verifier", "terminate", "abstain", "ask_for_spec")


def _bucket_reliability(r: float) -> str:
    return "high" if r >= 0.9 else ("medium" if r >= 0.5 else "low")


@dataclass(frozen=True)
class FoldedTaskSignature:
    task_regime: str        # bugfix | test_gen | refactor | security_fix | ...
    risk: str               # low | medium | high
    ambiguity: str          # clear | ambiguous
    evidence: str           # sufficient | insufficient
    reliability: str        # high | medium | low
    measurement: str        # trusted | untrusted

    def key(self) -> str:
        return "|".join((self.task_regime, self.risk, self.ambiguity, self.evidence,
                         self.reliability, self.measurement))


def fold(*, task_regime: str, risk: str = "low", spec_clarity: float = 1.0,
         evidence_sufficient: bool = True, single_shot_reliability: float = 1.0,
         measurement_quality: float = 1.0) -> FoldedTaskSignature:
    """Fold a task context into a compact signature (continuous dims bucketed)."""
    return FoldedTaskSignature(
        task_regime=task_regime, risk=risk,
        ambiguity="clear" if spec_clarity >= 0.5 else "ambiguous",
        evidence="sufficient" if evidence_sufficient else "insufficient",
        reliability=_bucket_reliability(single_shot_reliability),
        measurement="trusted" if measurement_quality >= 0.7 else "untrusted")


@dataclass
class _ActionStat:
    total_reward: float = 0.0
    n: int = 0

    def mean(self) -> float:
        return round(self.total_reward / self.n, 4) if self.n else 0.0


class PolicyGraph:
    """Signature -> action value, learned from conclusive rewards only; warm-startable."""

    def __init__(self) -> None:
        self._by_sig: dict[str, dict[str, _ActionStat]] = {}
        self._global: dict[str, _ActionStat] = {}

    def update(self, sig: FoldedTaskSignature, action: str, reward: float, *,
               conclusive: bool = True) -> None:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action}")
        if not conclusive:
            return  # measurement-trust invariant: only conclusive rewards update the policy
        s = self._by_sig.setdefault(sig.key(), {}).setdefault(action, _ActionStat())
        s.total_reward += reward
        s.n += 1
        g = self._global.setdefault(action, _ActionStat())
        g.total_reward += reward
        g.n += 1

    def value(self, sig: FoldedTaskSignature, action: str) -> tuple[float, int]:
        s = self._by_sig.get(sig.key(), {}).get(action)
        if s and s.n:
            return s.mean(), s.n
        g = self._global.get(action)
        return (g.mean(), g.n) if g else (0.0, 0)

    def best_action(self, sig: FoldedTaskSignature,
                    candidates: list | None = None) -> tuple[str, str]:
        cands = candidates or list(ACTIONS)
        scored = [(a, *self.value(sig, a)) for a in cands]
        seen = [t for t in scored if t[2] > 0]
        if not seen:
            return cands[0], "no evidence -> first candidate (cold start)"
        best = max(seen, key=lambda t: (t[1], t[2]))
        local = sig.key() in self._by_sig and best[0] in self._by_sig[sig.key()]
        return best[0], (f"value {best[1]} over n={best[2]} "
                         f"({'signature-local' if local else 'global fallback'})")

    def warm_start(self, other: PolicyGraph, *, weight: float = 0.5) -> None:
        """Transfer another graph's evidence (cross-repo/family) at a discount."""
        for key, actions in other._by_sig.items():
            dst = self._by_sig.setdefault(key, {})
            for action, st in actions.items():
                d = dst.setdefault(action, _ActionStat())
                d.total_reward += st.total_reward * weight
                d.n += max(1, int(st.n * weight))
        for action, st in other._global.items():
            g = self._global.setdefault(action, _ActionStat())
            g.total_reward += st.total_reward * weight
            g.n += max(1, int(st.n * weight))

    def to_dict(self) -> dict:
        return {"n_signatures": len(self._by_sig),
                "signatures": {k: {a: {"mean": s.mean(), "n": s.n}
                                   for a, s in acts.items()}
                               for k, acts in self._by_sig.items()},
                "global": {a: {"mean": s.mean(), "n": s.n}
                           for a, s in self._global.items()}}


def skip_policy(sig: FoldedTaskSignature) -> dict:
    """Which stages to skip for this signature. Verification is NEVER skipped on high risk."""
    skips: list[str] = []
    if sig.task_regime == "bugfix" and sig.risk == "low" and sig.ambiguity == "clear":
        skips.append("skip:planner")
    if sig.risk == "low" and sig.reliability == "high":
        skips.append("skip:retrieval")
    # never skip the reviewer/verifier on high-risk or untrusted measurement
    strict_verify = sig.risk == "high" or sig.measurement == "untrusted"
    return {"skips": skips, "strict_verify": strict_verify,
            "rationale": f"risk={sig.risk}, reliability={sig.reliability}, "
                         f"ambiguity={sig.ambiguity}"}


def reward_audit(promote_reward: float, audit_reward: float, *, max_disagreement: float = 0.2
                 ) -> dict:
    """A cross-judge reward audit: if the audit reward disagrees materially, block promotion."""
    disagreement = round(abs(promote_reward - audit_reward), 4)
    blocked = disagreement > max_disagreement or audit_reward < promote_reward - max_disagreement
    return {"promote_reward": promote_reward, "audit_reward": audit_reward,
            "disagreement": disagreement, "promotion_blocked": blocked,
            "reason": ("audit disagrees beyond tolerance -> block"
                       if blocked else "audit agrees -> allow")}
