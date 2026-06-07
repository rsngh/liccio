"""Meta-agent FinOps — policy cost report + promotion gate (GOALS Alpha 42 P6).

Turns a MetaRouter Arena report into a FinOps view: cost attribution per policy, advisor/
candidate waste, and a promotion gate that only promotes a router when it Pareto-improves the
incumbent on (verified success, cost per verified success). Pure functions over the arena dict.
"""

from __future__ import annotations

from typing import Any


def _by_policy(arena: dict) -> dict[str, dict]:
    return {s["policy"]: s for s in arena.get("policy_scores", [])}


def attribute_cost(arena: dict) -> dict[str, dict]:
    """Attribute each policy's spend across executor / advisor / candidate-sampling stages."""
    attempts = arena.get("attempts", [])
    out: dict[str, dict] = {}
    for pol, score in _by_policy(arena).items():
        rows = [a for a in attempts if a["policy"] == pol]
        total = sum(a["cost_usd"] for a in rows)
        advisor_rows = [a for a in rows if a.get("advisor_calls", 0) > 0]
        cand_rows = [a for a in rows if a.get("candidates_sampled", 0) > 0]
        # advisor/candidate runs cost more than a single executor pass; approximate their
        # share by the extra fraction of cost on rows that used them.
        base = [a for a in rows if a.get("advisor_calls", 0) == 0
                and a.get("candidates_sampled", 0) <= 1]
        base_avg = (sum(a["cost_usd"] for a in base) / len(base)) if base else 0.0
        advisor_extra = round(sum(max(0.0, a["cost_usd"] - base_avg) for a in advisor_rows), 6)
        candidates = sum(a.get("candidates_sampled", 0) for a in cand_rows)
        wasted = sum(a.get("candidates_sampled", 0) - (1 if a["solved"] else 0)
                     for a in cand_rows)
        out[pol] = {
            "total_cost_usd": round(total, 6),
            "cost_per_verified_success": score["cost_per_verified_success"],
            "executor_cost_usd": round(total - advisor_extra, 6),
            "advisor_cost_usd": advisor_extra,
            "advisor_cost_share": round(advisor_extra / total, 4) if total else 0.0,
            "candidates_sampled": candidates,
            "best_of_k_wasted_candidate_rate": round(wasted / candidates, 4) if candidates else 0.0,
        }
    return out


def promotion_decision(candidate: dict, incumbent: dict) -> dict:
    """A router is promotable only if it Pareto-improves the incumbent:
    verified rate up at no-worse cost/success, OR cost/success down at no-worse verified rate."""
    cv, iv = candidate["verified_success_rate"], incumbent["verified_success_rate"]
    cc = candidate["cost_per_verified_success"]
    ic = incumbent["cost_per_verified_success"]
    # if a policy never succeeds, cost/success is None -> treat as +inf for comparison
    cc_n = cc if cc is not None else float("inf")
    ic_n = ic if ic is not None else float("inf")
    better_quality_same_cost = cv > iv and cc_n <= ic_n
    cheaper_same_quality = cc_n < ic_n and cv >= iv
    promotable = bool(better_quality_same_cost or cheaper_same_quality)
    if promotable and better_quality_same_cost:
        reason = f"verified {iv}->{cv} at cost/success {ic}->{cc} (no cost regression)"
    elif promotable:
        reason = f"cost/success {ic}->{cc} at verified {iv}->{cv} (no quality regression)"
    else:
        reason = f"no Pareto improvement over incumbent (verified {cv} vs {iv}, cost {cc} vs {ic})"
    return {"candidate": candidate["policy"], "incumbent": incumbent["policy"],
            "promotable": promotable, "reason": reason}


def finops_report(arena: dict, *, incumbent: str = "cheap_single") -> dict[str, Any]:
    by_pol = _by_policy(arena)
    attribution = attribute_cost(arena)
    inc = by_pol.get(incumbent)
    # rank by verified success per dollar (success rate / cost-per-success; higher is better)
    def vspd(s: dict) -> float:
        cps = s["cost_per_verified_success"]
        return s["verified_success_rate"] / cps if cps else (s["verified_success_rate"] * 1e6)

    ranking = sorted(by_pol.values(), key=vspd, reverse=True)
    promotions = []
    if inc:
        for cand in by_pol.values():
            if cand["policy"] in (incumbent, "oracle"):
                continue
            promotions.append(promotion_decision(cand, inc))
    # best ROUTABLE policy excludes the calibration baselines (oracle ceiling / no-op floor)
    _calib = {"oracle", "cheap_static"}
    routable = [s for s in ranking if s["policy"] not in _calib]
    best = routable[0]["policy"] if routable else (ranking[0]["policy"] if ranking else None)
    return {
        "experiment": "finops_cost_per_verified_success",
        "incumbent": incumbent,
        "best_value_policy": best,
        "ranking_by_verified_success_per_dollar": [s["policy"] for s in ranking],
        "cost_attribution": attribution,
        "promotions": promotions,
        "promotable_policies": [p["candidate"] for p in promotions if p["promotable"]],
        "policy_scores": list(by_pol.values()),
    }
