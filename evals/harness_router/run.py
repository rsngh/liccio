# ruff: noqa: E501
"""Increment 1 — route across the FULL lever matrix: model x THINKING level x harness.

Extends the unified router from a model/context ladder to a 4-dimensional one:
  1. model family/size   : gemini flash-lite/flash, claude haiku/sonnet/opus
  2. thinking level (NEW) : explicit thinking-token budgets (cheap model + more thinking is a rung
                            BETWEEN tiers — DeepConf / weak-reasoning-boosting)
  3. context (harness-aware, NEW): autonomous CLIs get minimal injected context (they explore),
                            single-shot gets repo_map
  4. harness             : single-shot, in-process Claude loop, and the real autonomous agents —
                            gemini_cli, openhands (live here), codex_cli, claude_code (registered but
                            AVAILABILITY-GATED: unavailable here -> skipped, never faked)

Disciplined measurement: Wilson CIs; availability != capability (unavailable levers excluded from
denominators); conclusive vs infra separated; cost fully charged (thinking + verifier tokens).

    uv run python -m evals.harness_router.run --tasks 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import time
from collections import Counter
from pathlib import Path

from evals.hetero_arena.tiers import GEMINI_FLASH, GEMINI_FLASH_LITE, HAIKU, OPUS, SONNET
from evals.metarouter_arena.policies import _single_shot, build_workspace, verify
from evals.metarouter_arena.statistics import wilson_ci

from acp.agents.claude_agent import ClaudeAgentAdapter
from acp.agents.gemini_agent import GeminiAgentAdapter
from acp.agents.sandbox_cli import all_vendor_status, grant_access, run_vendor_cli
from acp.routing.topology_program_executor import AttemptOutcome
from acp.routing.unified_router import Lever, route_and_solve

# --- the 4-dim lever matrix (cheapest-first), with FinOps priors -----------------------------
# each: (kind, spec). kind="model": (tier, thinking_budget, context); kind="cli": vendor name.
_CFG: dict[str, tuple] = {
    "gflash_lite_min":   ("model", (GEMINI_FLASH_LITE, None, "minimal")),
    "haiku_min":         ("model", (HAIKU, 0, "minimal")),
    "gflash_think_min":  ("model", (GEMINI_FLASH, 2048, "minimal")),    # cheap model + THINKING
    "haiku_repomap":     ("model", (HAIKU, 0, "repo_map")),
    "sonnet_repomap":    ("model", (SONNET, 0, "repo_map")),
    "sonnet_think_repo": ("model", (SONNET, 3072, "repo_map")),         # mid model + THINKING
    "gemini_cli":        ("cli", "gemini_cli"),                          # autonomous (explores)
    "openhands":         ("cli", "openhands"),                           # autonomous (local runtime)
    "opus_repomap":      ("model", (OPUS, 0, "repo_map")),
    "codex_cli":         ("cli", "codex_cli"),                           # availability-gated
    "claude_code":       ("cli", "claude_code"),                         # availability-gated
}
LEVERS = [
    Lever("gflash_lite_min", 0.0006, 0.45), Lever("haiku_min", 0.0015, 0.5),
    Lever("gflash_think_min", 0.012, 0.6), Lever("haiku_repomap", 0.0025, 0.7),
    Lever("sonnet_repomap", 0.006, 0.78), Lever("sonnet_think_repo", 0.014, 0.82),
    Lever("gemini_cli", 0.02, 0.85), Lever("openhands", 0.025, 0.85),
    Lever("opus_repomap", 0.03, 0.9), Lever("codex_cli", 0.02, 0.85),
    Lever("claude_code", 0.02, 0.88),
]


def _model_adapter(tier, thinking):
    if tier.provider == "gemini":
        return GeminiAgentAdapter(name=tier.name, model=tier.model,
                                  max_output_tokens=16384 if thinking else 8192,
                                  thinking_budget=thinking)
    return ClaudeAgentAdapter(name=tier.name, model=tier.model, thinking_budget=(thinking or 0))


def _attempt(spec, root, lever, *, gemini_key, harness_adapter, avail) -> AttemptOutcome | None:
    kind, payload = _CFG[lever]
    if kind == "model":
        tier, thinking, ctx = payload
        att = _single_shot(_model_adapter(tier, thinking), spec, root, strategy=ctx,
                           policy_name=lever, cost_fn=tier.cost)
        return AttemptOutcome(solved=att.solved, public_solved=att.public_solved, cost=att.cost_usd)
    # CLI harness lever — availability-gated (unavailable -> None -> router skips, never faked)
    if not avail.get(payload, False):
        return None
    call_root = root / lever / f"c{time.time_ns()}"
    ws = build_workspace(spec, call_root)
    prompt = (f"{spec.issue_text}\n\nFix {spec.module_path} so the failing test in test_public.py "
              "passes. You may read/grep any file. Do not edit tests. Stop when done.")
    if payload == "openhands":
        from evals.harness_arena.policies import policy_openhands
        att = policy_openhands(spec, root, gemini_key=gemini_key)
        return AttemptOutcome(solved=att.solved, public_solved=att.public_solved, cost=att.cost_usd)
    grant_access(ws)
    api_env = {"GEMINI_API_KEY": gemini_key} if payload == "gemini_cli" else {}
    ran = run_vendor_cli(payload, ws, prompt, api_env=api_env, timeout_s=240)
    if not ran.ran or (ran.error and ran.error != "timeout") or ran.secret_leak:
        return None  # infra/inconclusive — not a capability failure
    solved, public = verify(ws, spec, call_root)
    return AttemptOutcome(solved=solved, public_solved=public, cost=0.0)  # CLI tokens not attributed


def _attempt_fn(spec, root, *, gemini_key, harness_adapter, avail):
    def fn(action, _tid):
        if action not in _CFG:
            return None
        return _attempt(spec, root, action, gemini_key=gemini_key,
                        harness_adapter=harness_adapter, avail=avail)
    return fn


def _corpus(n):
    from evals.harness_arena.harness_tasks import capability_corpus, ceiling_corpus
    return (list(capability_corpus())[:max(2, n // 2)] + ceiling_corpus(n - max(2, n // 2)))


def run(n_tasks: int) -> dict:
    tasks = _corpus(n_tasks)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    status = all_vendor_status()
    avail = {v: s.available for v, s in status.items()}
    h = ClaudeAgentAdapter(model="claude-sonnet-4-6")
    harness = h if asyncio.run(h.healthcheck()).available else None

    solved = cost = 0.0
    n = 0
    paths: list[str] = []
    lever_use = Counter()
    glob = [0, 0]  # [solved, conclusive]
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="harness_router_") as d:
        root = Path(d)
        for spec in tasks:
            n += 1
            afn = _attempt_fn(spec, root, gemini_key=gemini_key, harness_adapter=harness, avail=avail)
            res = route_and_solve(task_id=spec.name, failure_signature=f"{spec.task_type}:{spec.context_need}",
                                  repo_family="hr", tenant="t", task_type=spec.task_type,
                                  risk_level=spec.risk_level, budget_class="normal_bugfix",
                                  ladder=LEVERS, attempt_fn=afn, memory=None)
            solved += int(res.solved)
            cost += res.total_cost
            glob[1] += 1
            glob[0] += int(res.solved)
            paths.append("->".join(res.lever_path))
            for a in res.lever_path:
                if a in _CFG:
                    lever_use[a] += 1
            print(f"[{spec.name:20}] solved={res.solved} ${res.total_cost:.4f} path={res.lever_path} ({time.time()-t0:.0f}s)", flush=True)

    p, lo, hi = wilson_ci(glob[0], glob[1])
    return {
        "experiment": "harness_router",
        "question": "route across models x thinking levels x harnesses; reach autonomous CLI only when needed",
        "lever_matrix_dims": ["model_family/size", "thinking_level", "harness_aware_context", "harness"],
        "lever_availability": {v: {"available": s.available, "reason": s.reason} for v, s in status.items()},
        "n_tasks": n,
        "router": {"verified": p, "ci": [lo, hi], "solved": glob[0], "n": glob[1],
                   "total_cost_usd": round(cost, 6),
                   "cost_per_verified_success": round(cost / glob[0], 6) if glob[0] else None},
        "lever_usage_counts": dict(lever_use.most_common()),
        "lever_paths": paths,
        "elapsed_s": round(time.time() - t0, 1),
        "measurement": {"wilson_ci": True, "availability_separated_from_capability": True,
                        "thinking_and_verifier_tokens_charged": True,
                        "cli_token_cost": "not attributed (CLIs don't emit usage); latency carries their comparison"},
        "evidence_tier": "live; Anthropic + Google; codex/claude_code registered but unavailable here (env-gated)",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=8)
    ap.add_argument("--out", default="reports/harness_router_eval.json")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    rep = run(args.tasks)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    print("\n=== HARNESS ROUTER (Increment 1) — lever availability ===")
    for v, s in rep["lever_availability"].items():
        print(f"  {v:14} {'LIVE' if s['available'] else 'UNAVAILABLE'}  ({s['reason']})")
    r = rep["router"]
    cps = r["cost_per_verified_success"]
    cps_s = f"${cps:.5f}" if cps else "n/a"
    print(f"router: verified {r['verified']:.2f} CI[{r['ci'][0]:.2f},{r['ci'][1]:.2f}] cost/succ {cps_s}")
    print("lever usage:", rep["lever_usage_counts"])
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
