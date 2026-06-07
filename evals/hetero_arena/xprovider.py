# ruff: noqa: E501
"""Cross-PROVIDER heterogeneity — the strongest form of the #1 gap.

The earlier arena varied only Anthropic tiers. This varies the PROVIDER FAMILY too: Google's
gemini-2.5-flash/pro alongside Claude haiku/sonnet/opus. Now "use the cheapest capable model" can
cross vendor boundaries, and provider DIVERSITY (sample two different families, keep whichever
verifies) becomes testable. Every call is single-shot live; cost is each tier's real published
price. Honest by construction: if the globally-cheapest tier already solves everything, the finding
is "route to it across providers and save" — not dressed up as a capability win.

    uv run python -m evals.hetero_arena.xprovider --trials 2
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from evals.hetero_arena.tier_tasks import all_capability_tasks
from evals.hetero_arena.tiers import (
    GEMINI_FLASH,
    GEMINI_FLASH_LITE,
    GEMINI_PRO,
    HAIKU,
    OPUS,
    SONNET,
)
from evals.metarouter_arena.policies import _single_shot
from evals.metarouter_arena.schema import AdapterStatus, ArenaAttempt
from evals.metarouter_arena.statistics import wilson_ci

# cheapest-first across BOTH provider families (ascending output price):
# gemini-flash-lite($0.40) < gemini-flash($2.50) < haiku($5) < gemini-pro($12) < sonnet($15) < opus($75)
LADDER = [GEMINI_FLASH_LITE, GEMINI_FLASH, HAIKU, GEMINI_PRO, SONNET, OPUS]
SINGLE_TIERS = [GEMINI_FLASH_LITE, GEMINI_FLASH, HAIKU, SONNET, GEMINI_PRO, OPUS]


def _ci(s, n):
    return dict(zip(("point", "lo", "hi"), wilson_ci(s, n), strict=False))


def _single(tier, spec, root):
    return _single_shot(tier.adapter(), spec, root, strategy="minimal",
                        policy_name=f"x_{tier.name}", cost_fn=tier.cost)


def policy_cross_provider_escalation(spec, root) -> ArenaAttempt:
    """Cheapest-capable across providers: flash->haiku->pro->sonnet->opus, stop on public pass."""
    t0 = time.time()
    total = 0.0
    path: list[str] = []
    last = None
    for tier in LADDER:
        a = _single(tier, spec, root)
        total += a.cost_usd
        path.append(tier.name)
        last = a
        if not a.conclusive:
            continue
        if a.public_solved:
            break
    return ArenaAttempt(task=spec.name, policy="cross_provider_escalation",
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value if last.conclusive else AdapterStatus.LIVE_INCONCLUSIVE.value,
                        solved=last.solved, public_solved=last.public_solved, conclusive=last.conclusive,
                        cost_usd=round(total, 6), latency_s=round(time.time() - t0, 2),
                        candidates_sampled=len(path), detail="->".join(path))


def policy_best_of_providers(spec, root) -> ArenaAttempt:
    """Provider diversity: one gemini-flash-lite + one haiku (cheapest of each family); select by
    public-test signal. Tests whether cross-family diversity rescues what one family fails."""
    t0 = time.time()
    cands = [_single(GEMINI_FLASH_LITE, spec, root), _single(HAIKU, spec, root)]
    cost = round(sum(c.cost_usd for c in cands), 6)
    conclusive = any(c.conclusive for c in cands)
    chosen = next((c for c in cands if c.public_solved),
                  next((c for c in cands if c.conclusive), cands[0]))
    return ArenaAttempt(task=spec.name, policy="best_of_providers",
                        adapter_status=AdapterStatus.LIVE_CONCLUSIVE.value if conclusive else AdapterStatus.LIVE_INCONCLUSIVE.value,
                        solved=chosen.solved, public_solved=chosen.public_solved, conclusive=conclusive,
                        cost_usd=cost, latency_s=round(time.time() - t0, 2), candidates_sampled=2,
                        detail="flash+haiku diversity by public proof")


def run(trials: int) -> dict:
    tasks = all_capability_tasks()
    glob: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    cost: dict[str, float] = defaultdict(float)
    per_task: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    extra = {"cross_provider_escalation": policy_cross_provider_escalation,
             "best_of_providers": policy_best_of_providers}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="xprov_") as d:
        root = Path(d)
        for tr in range(trials):
            for spec in tasks:
                for tier in SINGLE_TIERS:
                    a = _single(tier, spec, root)
                    _tally(glob, cost, per_task, f"{tier.name}_single", spec.name, a)
                for pname, fn in extra.items():
                    a = fn(spec, root)
                    _tally(glob, cost, per_task, pname, spec.name, a)
                print(f"[xprov t{tr}] {spec.name} ({time.time()-t0:.0f}s)", flush=True)

    rows = {}
    for name, (s, c) in glob.items():
        cps = round(cost[name] / s, 6) if s else None
        rows[name] = {"verified": round(s / c, 4) if c else 0.0, "ci": _ci(s, c),
                      "n_conclusive": c, "total_cost_usd": round(cost[name], 6),
                      "cost_per_verified_success": cps}
    # cheapest tier that is statistically at-ceiling (verified CI lower bound highest / cost lowest)
    ranked = sorted(rows.items(), key=lambda kv: (kv[1]["cost_per_verified_success"] or 9e9))
    return {
        "experiment": "hetero_arena_xprovider",
        "providers": {"anthropic": ["haiku", "sonnet", "opus"],
                      "gemini": ["gemini_flash_lite", "gemini_flash", "gemini_pro"]},
        "tiers_priced": {t.name: {"model": t.model, "provider": t.provider,
                                  "in_per_mtok": round(t.in_per_tok * 1e6, 4),
                                  "out_per_mtok": round(t.out_per_tok * 1e6, 4)}
                         for t in SINGLE_TIERS},
        "trials": trials, "n_tasks": len(tasks), "elapsed_s": round(time.time() - t0, 1),
        "scores": rows,
        "cheapest_per_success_ranking": [k for k, _ in ranked],
        "per_task": {t: {p: {"verified": round(v[0] / v[1], 4) if v[1] else 0.0, "n": v[1]}
                         for p, v in by.items()} for t, by in per_task.items()},
        "gemini_status": "LIVE (reachable this run): gemini-2.5-flash/pro generateContent OK",
    }


def _tally(glob, cost, per_task, name, task, a) -> None:
    cost[name] += a.cost_usd
    if a.conclusive:
        glob[name][1] += 1
        per_task[task][name][1] += 1
        if a.solved:
            glob[name][0] += 1
            per_task[task][name][0] += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument("--out", default="reports/hetero_arena_xprovider.json")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    rep = run(args.trials)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    print("\n=== CROSS-PROVIDER ARENA ===")
    for name in rep["cheapest_per_success_ranking"]:
        r = rep["scores"][name]
        cps = r["cost_per_verified_success"]
        print(f"{name:26} verified {r['verified']:.2f} CI[{r['ci']['lo']:.2f},{r['ci']['hi']:.2f}] "
              f"cost/success ${cps:.5f}" if cps else f"{name:26} verified {r['verified']:.2f} (no success)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
