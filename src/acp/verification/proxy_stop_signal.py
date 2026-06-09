# ruff: noqa: E501
"""Production stop signal built on the independent proxy verifier (GOALS P1).

The verifier proxy is the measured binding constraint on routing: the parts existed in
isolation but nothing composed them into the ONE decision the production loop makes once
k candidates exist. This module is that composition:

  * :func:`decide` selects the minimal PROXY-verified candidate via
    :func:`comparator_strength.select_best_online` — so a public-only signal can never
    promote a candidate where the held-out proxy contradicts it;
  * it CHARGES the proxy's own cost (independent-test generation + check execution) so the
    verifier is never "free" in FinOps accounting (the eval measured this at ~+7%);
  * it derives a calibrated confidence from the proxy evidence and routes to HUMAN REVIEW
    when no candidate clears the proxy or the confidence is low — never a silent
    public-only auto-commit. The commit/abstain/human_review bar is the risk-calibrated
    one from :func:`verification.calibrated_stop`.

:func:`proxy_health_by_family` is the health gate: given labelled (proxy vs true hidden)
outcomes, it reports the proxy's precision/recall PER TASK FAMILY, so a family where the
proxy is unreliable is visible (and can be forced to human review) instead of silently
promoting wrong candidates.

Deterministic and dependency-free: callers pass already-computed
:class:`independent_proof.ProxyVerdict` objects and candidate metadata, so this is unit
testable without any LLM or subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.evaluation.comparator_strength import (
    Candidate,
    ComparatorResult,
    select_best_online,
)
from acp.verification.calibrated_stop import StopDecision, calibrated_stop
from acp.verification.independent_proof import ProxyVerdict


@dataclass
class ProxyStopSignal:
    """The composed decision: which candidate (if any) to commit, and how confidently."""

    action: str                      # commit | abstain | human_review
    selected: str | None
    selected_proxy_pass: bool
    confidence: float
    sufficiency: float
    proxy_cost_usd: float
    comparator: ComparatorResult
    stop: StopDecision
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "selected": self.selected,
            "selected_proxy_pass": self.selected_proxy_pass,
            "confidence": self.confidence,
            "sufficiency": self.sufficiency,
            "proxy_cost_usd": round(self.proxy_cost_usd, 6),
            "selected_verified": self.comparator.selected_verified,
            "n_candidates": self.comparator.n_candidates,
            "n_rejected": self.comparator.n_rejected,
            "reject_reasons": self.comparator.reject_reasons,
            "stop_reason": self.stop.reason,
            "reason": self.reason,
        }


def proxy_confidence(verdict: ProxyVerdict | None, *, target_checks: int = 3) -> tuple[float, float]:
    """Calibrated (judge_confidence, sufficiency) for the chosen candidate's proxy evidence.

    * judge_confidence — fraction of the *surviving* independent checks the candidate passes.
      Zeroed if it failed public or tripped an adversarial-high finding (no benefit of the
      doubt for gamed diffs).
    * sufficiency — how much independent evidence existed: ``min(1, surviving/target_checks)``.
      With no runnable independent checks the proxy has only the public test, so sufficiency
      is low and :func:`calibrated_stop` will route to human review rather than auto-commit.
    """
    if verdict is None or not verdict.public_pass or verdict.adversarial_high:
        return 0.0, 0.0
    surviving = verdict.n_checks_surviving
    if surviving <= 0:
        # public passed but no independent corroboration — weak evidence
        return 0.5, 0.0
    passing = surviving - verdict.n_checks_failed
    judge = round(max(0.0, passing) / surviving, 4)
    sufficiency = round(min(1.0, surviving / max(1, target_checks)), 4)
    return judge, sufficiency


def decide(
    candidates: list[Candidate],
    verdicts: dict[str, ProxyVerdict],
    *,
    gen_cost_usd: float = 0.0,
    run_cost_usd: float = 0.0,
    risk_level: str = "low",
    target_checks: int = 3,
) -> ProxyStopSignal:
    """Compose proxy verdicts -> selection -> calibrated commit/human-review, charging proxy cost.

    ``candidates`` are :class:`comparator_strength.Candidate`; each ``proxy_pass`` is taken from
    ``verdicts`` (so the caller cannot accidentally select on public-only). ``gen_cost_usd`` is the
    LLM cost of generating the independent checks; ``run_cost_usd`` any compute cost of running them
    — both are charged into ``proxy_cost_usd`` so the verifier shows up in FinOps.
    """
    for c in candidates:
        v = verdicts.get(c.id)
        if v is not None:
            c.proxy_pass = v.proxy_pass

    comp = select_best_online(candidates)
    proxy_cost = round(gen_cost_usd + run_cost_usd, 6)

    chosen_verdict = verdicts.get(comp.selected) if comp.selected else None
    selected_proxy_pass = bool(chosen_verdict and chosen_verdict.proxy_pass)

    # No proxy-verified candidate -> the public-only signal is all we have. Never auto-commit it:
    # force human review (this is the "cannot promote on public-only where proxy exists" rule).
    if not selected_proxy_pass:
        stop = StopDecision("human_review", 0.0, "no proxy-verified candidate")
        return ProxyStopSignal(
            action="human_review", selected=comp.selected, selected_proxy_pass=False,
            confidence=0.0, sufficiency=0.0, proxy_cost_usd=proxy_cost, comparator=comp,
            stop=stop, reason="no candidate cleared the independent proxy")

    judge, sufficiency = proxy_confidence(chosen_verdict, target_checks=target_checks)
    stop = calibrated_stop(judge_confidence=judge, sufficiency_score=sufficiency, risk_level=risk_level)
    return ProxyStopSignal(
        action=stop.action, selected=comp.selected, selected_proxy_pass=True,
        confidence=stop.confidence, sufficiency=sufficiency, proxy_cost_usd=proxy_cost,
        comparator=comp, stop=stop, reason=stop.reason)


# --- health gate: proxy precision/recall per task family -------------------------------------


@dataclass
class ProxyHealth:
    family: str
    n: int
    proxy_positives: int        # predicted-correct by the proxy
    true_positives: int         # proxy_pass AND truly hidden_pass
    false_positives: int        # proxy_pass BUT hidden_fail (the dangerous error)
    false_negatives: int        # proxy_fail BUT hidden_pass (over-cautious; sent to humans)
    precision: float            # TP / (TP + FP) — trust that a proxy-pass is really correct
    recall: float               # TP / (TP + FN) — coverage of truly-correct candidates

    def to_dict(self) -> dict:
        return {
            "family": self.family, "n": self.n, "proxy_positives": self.proxy_positives,
            "true_positives": self.true_positives, "false_positives": self.false_positives,
            "false_negatives": self.false_negatives, "precision": self.precision,
            "recall": self.recall,
        }


def proxy_health_by_family(samples: list[dict]) -> dict[str, ProxyHealth]:
    """Precision/recall of the proxy against the true hidden oracle, bucketed by task family.

    ``samples`` items: ``{"family": str, "proxy_pass": bool, "hidden_pass": bool}``. A family with
    low precision is one where the proxy promotes wrong candidates — the signal to force human
    review (or strengthen the verifier) there rather than trust it.
    """
    buckets: dict[str, list[dict]] = {}
    for s in samples:
        buckets.setdefault(str(s.get("family", "_all")), []).append(s)
    out: dict[str, ProxyHealth] = {}
    for fam, rows in buckets.items():
        tp = sum(1 for r in rows if r["proxy_pass"] and r["hidden_pass"])
        fp = sum(1 for r in rows if r["proxy_pass"] and not r["hidden_pass"])
        fn = sum(1 for r in rows if not r["proxy_pass"] and r["hidden_pass"])
        precision = round(tp / (tp + fp), 4) if (tp + fp) else 1.0
        recall = round(tp / (tp + fn), 4) if (tp + fn) else 1.0
        out[fam] = ProxyHealth(
            family=fam, n=len(rows), proxy_positives=tp + fp, true_positives=tp,
            false_positives=fp, false_negatives=fn, precision=precision, recall=recall)
    return out
