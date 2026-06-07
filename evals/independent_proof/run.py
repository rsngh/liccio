# ruff: noqa: E501
"""Phase 1 eval — does an INDEPENDENT proxy verifier beat public-only selection per dollar?

Pipeline per task: generate k diverse candidates from a MIX of weak/strong models (so over-fits are
uncorrelated), record each candidate's public_pass, the held-out hidden verdict (oracle, for
MEASUREMENT only), and its diff. Generate independent tests from the spec (a cheap LLM, never seeing
the candidate/hidden). Score every candidate with the proxy (independent tests + differential
consensus + adversarial scan). Then run three selectors and grade the CHOSEN candidate by the true
hidden test:

  * public_only : first public-passing candidate            (today's weak signal)
  * proxy       : minimal proxy-verified candidate          (this work — no oracle used)
  * oracle      : minimal hidden-verified candidate          (upper bound)

Reports realized verified-success + cost (candidate cost + proxy's own check-gen cost) per selector,
and the proxy's precision/recall vs the hidden oracle. Honest: the proxy is never claimed to equal
the hidden test.

    uv run python -m evals.independent_proof.run --k 5 --tasks 12
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from evals.hetero_arena.tier_tasks import all_capability_tasks
from evals.hetero_arena.tiers import GEMINI_FLASH, GEMINI_FLASH_LITE, HAIKU
from evals.metarouter_arena.policies import build_workspace, verify
from evals.metarouter_arena.statistics import wilson_ci

from acp.evaluation.comparator_strength import (
    Candidate,
    select_best,
    select_best_online,
)
from acp.schemas.agent import Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.verification.independent_proof import generate_checks, proxy_evaluate
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

# diverse roster: weak (over-fit-prone) + mid, so consensus has uncorrelated errors to work with
ROSTER = [GEMINI_FLASH_LITE, GEMINI_FLASH_LITE, HAIKU, HAIKU, GEMINI_FLASH]


def _make_candidate(tier, spec, root, idx):
    """Run one model on the task; return (workspace, public_pass, hidden_pass, diff, cost)."""
    call_root = root / f"cand_{idx}_{time.time_ns()}"
    ws = build_workspace(spec, call_root)
    items = [ContextItem(kind="instruction_chunk", path="__task_spec__", content=spec.issue_text, source="task"),
             ContextItem(kind="file_chunk", path=spec.module_path, content=spec.buggy)]
    pack = ContextPack(repo_id="r", task_id="t", snapshot_id="s", strategy="minimal", items=items)
    repo = Repository(name=spec.name, local_path=str(ws), default_branch="master")
    from git import Repo
    base = Repo(ws).head.commit.hexsha
    wsx = LocalWorkspaceManager(call_root / "work").create(
        repo, RepoSnapshot(repo_id=repo.id, base_commit=base), default_policy())
    task = Task(repo_id=repo.id, title=f"Fix {spec.module_path}", body=spec.issue_text)
    adapter = tier.adapter()
    try:
        res = asyncio.run(adapter.execute(task, pack, wsx, Budget(max_cost_usd=0.3, max_wall_time_s=60)))
    except Exception:  # noqa: BLE001
        return None
    workspace = Path(wsx.path)
    hidden, public = verify(workspace, spec, call_root)
    diff = res.diff.unified_diff if res.diff else ""
    cost = tier.cost(res.input_token_count, res.output_token_count)
    return {"id": f"{tier.name}_{idx}", "workspace": workspace, "public_pass": public,
            "hidden_pass": hidden, "diff": diff, "cost": cost, "strategy": tier.name}


def _anthropic_client():
    from acp.agents.claude_agent import ClaudeAgentAdapter
    return ClaudeAgentAdapter()._client()


def run(n_tasks: int, k: int) -> dict:
    tasks = all_capability_tasks()
    # prefer the harder tasks (where weak models over-fit) — hard/heavy first
    tasks = sorted(tasks, key=lambda t: {"easy": 2, "medium": 1, "hard": 0}.get(t.difficulty_band, 0))[:n_tasks]
    client = _anthropic_client()
    roster = (ROSTER * ((k // len(ROSTER)) + 1))[:k]

    sel_solved = {"public_only": 0, "proxy": 0, "oracle": 0}
    sel_cost = {"public_only": 0.0, "proxy": 0.0, "oracle": 0.0}
    sel_n = 0
    # proxy-vs-hidden confusion over ALL candidates
    tp = fp = tn = fn = 0
    check_cost_total = 0.0
    per_task = {}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="indep_proof_") as d:
        root = Path(d)
        for spec in tasks:
            cands = [c for c in (_make_candidate(roster[i], spec, root, i) for i in range(k)) if c]
            if not cands:
                continue
            gen = generate_checks(spec, client=client, n=6)
            check_cost_total += gen.cost_usd
            verdicts = proxy_evaluate(spec, [{"id": c["id"], "workspace": c["workspace"],
                                              "public_pass": c["public_pass"], "diff": c["diff"]}
                                             for c in cands], root, checks=gen.checks)
            # build comparator candidates (proxy + oracle views)
            cmp_cands = []
            for c in cands:
                v = verdicts[c["id"]]
                cmp_cands.append(Candidate(id=c["id"], public_pass=c["public_pass"],
                                           hidden_pass=c["hidden_pass"],
                                           diff_lines=max(1, c["diff"].count("\n")),
                                           strategy=c["strategy"], cost=c["cost"],
                                           proxy_pass=v.proxy_pass))
                # confusion: proxy_pass (pred) vs hidden_pass (truth), only where conclusive
                pred, truth = v.proxy_pass, c["hidden_pass"]
                tp += int(pred and truth)
                fp += int(pred and not truth)
                tn += int(not pred and not truth)
                fn += int(not pred and truth)
            by_id = {c["id"]: c for c in cands}
            total_gen_cost = sum(c["cost"] for c in cands)
            # selectors
            pub = next((c for c in cands if c["public_pass"]), cands[0])
            proxy_res = select_best_online(cmp_cands)
            oracle_res = select_best(cmp_cands)
            chosen = {
                "public_only": (by_id[pub["id"]]["hidden_pass"], total_gen_cost),
                "proxy": (by_id[proxy_res.selected]["hidden_pass"] if proxy_res.selected else False,
                          total_gen_cost + gen.cost_usd),
                "oracle": (by_id[oracle_res.selected]["hidden_pass"] if oracle_res.selected else False,
                           total_gen_cost),
            }
            sel_n += 1
            for name, (solved, cost) in chosen.items():
                sel_solved[name] += int(solved)
                sel_cost[name] += cost
            per_task[spec.name] = {n: int(s) for n, (s, _c) in chosen.items()}
            print(f"[{spec.name:18}] pub={chosen['public_only'][0]} proxy={chosen['proxy'][0]} "
                  f"oracle={chosen['oracle'][0]} checks={len(gen.checks)} ({time.time()-t0:.0f}s)", flush=True)

    def _rate(num):
        p, lo, hi = wilson_ci(num, sel_n)
        return {"solved": num, "n": sel_n, "rate": p, "ci": [lo, hi]}

    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None
    return {
        "experiment": "independent_proof",
        "question": "does an independent proxy verifier beat public-only candidate selection per dollar?",
        "n_tasks": sel_n, "k_candidates": k, "roster": [t.name for t in roster],
        "elapsed_s": round(time.time() - t0, 1),
        "selectors": {name: {**_rate(sel_solved[name]),
                             "total_cost_usd": round(sel_cost[name], 6),
                             "cost_per_verified_success": round(sel_cost[name] / sel_solved[name], 6) if sel_solved[name] else None}
                      for name in ("public_only", "proxy", "oracle")},
        "proxy_vs_hidden_oracle": {"precision": precision, "recall": recall,
                                   "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                                   "note": "pred=proxy_pass, truth=hidden_pass over all candidates"},
        "proxy_check_gen_cost_usd": round(check_cost_total, 6),
        "per_task": per_task,
        "evidence_tier": "live; candidates from a weak/strong model mix; proxy never sees the hidden test",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=12)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out", default="reports/independent_proof_eval.json")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    rep = run(args.tasks, args.k)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    print("\n=== INDEPENDENT PROOF (Phase 1) ===")
    for name, s in rep["selectors"].items():
        cps = s["cost_per_verified_success"]
        cps_s = f"${cps:.5f}" if cps else "n/a"
        print(f"{name:12} verified {s['rate']:.2f} CI[{s['ci'][0]:.2f},{s['ci'][1]:.2f}] "
              f"cost/succ {cps_s}")
    pr = rep["proxy_vs_hidden_oracle"]
    print(f"proxy vs hidden oracle: precision={pr['precision']} recall={pr['recall']} (tp={pr['tp']} fp={pr['fp']} fn={pr['fn']})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
