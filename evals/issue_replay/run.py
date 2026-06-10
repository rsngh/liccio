# ruff: noqa: E501
"""Live issue-replay runner + patch-equivalence judge (GOALS P3).

The replay bundles (``replay_task.frozen_bundles``) are shaped like real GitHub issue->fixing-PR
replay: buggy base state, a withheld gold patch, public + held-out hidden tests. Until now the
code only VALIDATED their fairness. This runs a LIVE single-shot model over each bundle with only
the issue text + buggy module as context (gold patch and hidden tests withheld), then grades the
produced module by:

  * the held-out HIDDEN test (the correctness oracle), and
  * semantic PATCH-EQUIVALENCE to the withheld gold patch (same outputs on probe inputs derived
    from the bundle's own tests).

Cheap by construction — one cheap-tier call per bundle. Honest evidence tier: the bundles are
labelled (frozen_synthetic vs real_issue_replay) and the report carries the per-source breakdown,
so synthetic bundles can never masquerade as scraped real history.

    uv run python -m evals.issue_replay.run --model gemini --out reports/issue_replay_live.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from evals.issue_replay.replay_runner import patch_equivalent, verify
from evals.issue_replay.replay_task import IssueReplayTask, frozen_bundles
from evals.metarouter_arena.statistics import wilson_ci
from git import Repo

from acp.schemas.agent import Budget
from acp.schemas.context import ContextItem, ContextPack
from acp.schemas.repo import Repository, RepoSnapshot
from acp.schemas.task import Task
from acp.workspaces.local import LocalWorkspaceManager
from acp.workspaces.policies import default_policy

# model id + (in,out) USD-per-token published price
_MODELS = {
    "gemini": ("gemini-3-flash-preview", (0.30e-6, 2.50e-6)),
    "haiku": ("claude-haiku-4-5", (1e-6, 5e-6)),
    "sonnet": ("claude-sonnet-4-6", (3e-6, 15e-6)),
    "opus": ("claude-opus-4-8", (15e-6, 75e-6)),
}


def _adapter(model: str):
    model_id = _MODELS[model][0]
    if model == "gemini":
        from acp.agents.gemini_agent import GeminiAgentAdapter
        return GeminiAgentAdapter(name="gemini", model=model_id, thinking_budget=0)
    from acp.agents.claude_agent import ClaudeAgentAdapter
    return ClaudeAgentAdapter(name=model, model=model_id)


def _probes_from_tests(task: IssueReplayTask) -> list[str]:
    """Reuse the bundle's own test call-sites as equivalence probes: rewrite ``name(args)`` to
    ``m.name(args)`` (for each top-level symbol the tests import from the module) so produced vs
    gold modules can be compared on identical inputs. Class-valued symbols generally won't compare
    equal by repr and are simply not corroborated — reported honestly per bundle."""
    text = task.public_test + "\n" + task.hidden_test
    # symbols imported from the module under test, e.g. `from dates import offset_minutes`
    mod = task.module_path[:-3]
    names: list[str] = []
    for m in re.finditer(rf"from\s+{re.escape(mod)}\s+import\s+([^\n]+)", text):
        names += [n.strip() for n in m.group(1).split(",") if n.strip().isidentifier()]
    names = names or [mod]
    probes: list[str] = []
    for fn in names:
        for m in re.finditer(rf"\b{re.escape(fn)}\s*\(", text):
            start = m.end() - 1
            depth, i = 0, start
            while i < len(text):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            probes.append(f"m.{fn}{text[start:i + 1]}")
    # dedupe, preserve order
    seen: set[str] = set()
    return [p for p in probes if not (p in seen or seen.add(p))]


def _produce(task: IssueReplayTask, model: str, root: Path) -> tuple[str, float, bool]:
    """Run a live single-shot model on the bundle; return (produced_module_src, cost_usd, ran)."""
    src = root / f"src_{abs(hash(task.repo_name)) % 10_000}_{time.time_ns()}"
    src.mkdir(parents=True, exist_ok=True)
    (src / task.module_path).parent.mkdir(parents=True, exist_ok=True)  # package bundles: nested module_path
    (src / task.module_path).write_text(task.buggy)
    for p, c in task.extra_files.items():
        (src / p).parent.mkdir(parents=True, exist_ok=True)
        (src / p).write_text(c)
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add([task.module_path, *task.extra_files.keys()])
    repo.index.commit("base")
    mgr = LocalWorkspaceManager(src / "ws")
    r = Repository(name=task.repo_name, local_path=str(src), default_branch="master")
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha),
                    default_policy())
    items = [ContextItem(kind="instruction_chunk", path="__issue__",
                         content=f"{task.issue_title}\n\n{task.issue_body}", source="task"),
             ContextItem(kind="file_chunk", path=task.module_path, content=task.buggy)]
    for p, c in task.extra_files.items():
        items.append(ContextItem(kind="file_chunk", path=p, content=c))
    pack = ContextPack(repo_id="r", task_id="t", snapshot_id="s", strategy="minimal", items=items)
    t = Task(repo_id=r.id, title=task.issue_title, body=task.issue_body)
    try:
        res = asyncio.run(_adapter(model).execute(
            t, pack, ws, Budget(max_cost_usd=0.3, max_wall_time_s=60)))
    except Exception:  # noqa: BLE001 - a failed call -> no change -> unsolved
        return task.buggy, 0.0, False
    produced = (Path(ws.path) / task.module_path)
    out = produced.read_text() if produced.exists() else task.buggy
    rate_in, rate_out = _MODELS[model][1]
    cost = round((res.input_token_count or 0) * rate_in + (res.output_token_count or 0) * rate_out, 6)
    return out, cost, True


def _produce_harness(task: IssueReplayTask, model: str, root: Path, *, max_steps: int) -> tuple[str, float, bool]:
    """Run ACP's in-process Claude tool-loop HARNESS on the bundle. Unlike single-shot, the harness
    can read files, run the repo's tests, and iterate. The repo's real test file is placed in the
    workspace as a runnable repro (``test_repro.py``) so the harness has a failing test to converge
    on; grading still uses the bundle's pristine hidden test against the PRODUCED MODULE, so editing
    the workspace test cannot fool the score."""
    from acp.agents.claude_harness import ClaudeHarnessAdapter
    src = root / f"h_{abs(hash(task.repo_name + task.issue_title)) % 10_000}_{time.time_ns()}"
    src.mkdir(parents=True, exist_ok=True)
    (src / task.module_path).parent.mkdir(parents=True, exist_ok=True)  # package bundles: nested module_path
    (src / task.module_path).write_text(task.buggy)
    for p, c in task.extra_files.items():
        (src / p).parent.mkdir(parents=True, exist_ok=True)
        (src / p).write_text(c)
    (src / "conftest.py").write_text("import os, sys\nsys.path.insert(0, os.path.dirname(__file__))\n")
    (src / "test_repro.py").write_text(task.hidden_test)
    repo = Repo.init(src)
    repo.config_writer().set_value("user", "name", "t").release()
    repo.config_writer().set_value("user", "email", "t@e.com").release()
    repo.index.add([task.module_path, "conftest.py", "test_repro.py", *task.extra_files.keys()])
    repo.index.commit("base")
    mgr = LocalWorkspaceManager(src / "ws")
    r = Repository(name=task.repo_name, local_path=str(src), default_branch="master")
    ws = mgr.create(r, RepoSnapshot(repo_id=r.id, base_commit=repo.head.commit.hexsha), default_policy())
    items = [ContextItem(kind="instruction_chunk", path="__issue__",
                         content=f"{task.issue_title}\n\n{task.issue_body}\n\n"
                                 f"The failing tests are in test_repro.py. Fix {task.module_path} so they pass; "
                                 "do not edit the tests.", source="task")]
    pack = ContextPack(repo_id="r", task_id="t", snapshot_id="s", strategy="minimal", items=items)
    t = Task(repo_id=r.id, title=task.issue_title, body=task.issue_body)
    # the harness is a Claude tool-loop; use the requested claude tier, else haiku
    hmodel = _MODELS[model][0] if model in ("haiku", "sonnet", "opus") else "claude-haiku-4-5"
    try:
        res = asyncio.run(ClaudeHarnessAdapter(model=hmodel, max_steps=max_steps).execute(
            t, pack, ws, Budget(max_cost_usd=0.8, max_wall_time_s=240)))
    except Exception:  # noqa: BLE001 - a failed loop -> no change -> unsolved
        return task.buggy, 0.0, False
    produced = Path(ws.path) / task.module_path
    out = produced.read_text() if produced.exists() else task.buggy
    rate = _MODELS.get(model if model in ("haiku", "sonnet", "opus") else "haiku")[1]
    cost = round((res.input_token_count or 0) * rate[0] + (res.output_token_count or 0) * rate[1], 6)
    return out, cost, True


def _produce_vendor(task: IssueReplayTask, agent: str, root: Path, *, timeout_s: int = 300) -> tuple[str, float, bool]:
    """Drive a real stateful CLI coding agent (claude_code / codex_cli / gemini_cli) on the bundle.

    The agent runs in a git repo containing the buggy module + the failing test as a runnable repro;
    it localizes/edits/iterates natively. Env is subscription-safe (vendor_native.vendor_env strips
    ANTHROPIC_API_KEY for claude_code). Grading is unchanged (pristine hidden test on the produced
    module), so the agent editing the in-repo test cannot game the score."""
    from acp.agents.vendor_native import VendorNativeHarness
    h = VendorNativeHarness(agent)
    if not h.available():
        return task.buggy, 0.0, False
    src = root / f"v_{agent}_{abs(hash(task.repo_name + task.issue_title)) % 10000}_{time.time_ns()}"
    src.mkdir(parents=True, exist_ok=True)
    (src / task.module_path).parent.mkdir(parents=True, exist_ok=True)  # package bundles: nested module_path
    (src / task.module_path).write_text(task.buggy)
    for p, c in task.extra_files.items():
        (src / p).parent.mkdir(parents=True, exist_ok=True)
        (src / p).write_text(c)
    (src / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\n")
    (src / "test_repro.py").write_text(task.hidden_test)
    repo = Repo.init(src)
    cw = repo.config_writer()
    cw.set_value("user", "name", "t")
    cw.set_value("user", "email", "t@e.com")
    cw.set_value("commit", "gpgsign", "false")
    cw.release()
    repo.index.add([task.module_path, "conftest.py", "test_repro.py", *task.extra_files.keys()])
    repo.index.commit("base")
    prompt = (f"{task.issue_title}\n\n{task.issue_body}\n\nThe failing tests are in test_repro.py. "
              f"Fix {task.module_path} so they pass. Do not edit the tests.")
    res = h.run_task(src, prompt, timeout_s=timeout_s)
    produced = src / task.module_path
    out = produced.read_text() if produced.exists() else task.buggy
    # claude_code + codex run on the subscription (quota, not metered $ here); gemini_cli is API-key
    # but the CLI doesn't surface tokens -> cost recorded 0.0 and noted in the report's evidence tier.
    return out, 0.0, (not res.timed_out and res.error is None)


def run(model: str, bundles: list[IssueReplayTask], *, mode: str = "single", max_steps: int = 14,
        delay_s: float = 0.0, agent: str = "") -> dict:
    solved = equiv = ran = 0
    total_cost = 0.0
    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])   # [solved, n]
    per_bundle = []
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="issue_replay_live_") as d:
        root = Path(d)
        for bi, b in enumerate(bundles):
            if delay_s and bi:
                time.sleep(delay_s)   # throttle between bundles to avoid provider rate limits
            if mode == "repair":
                from evals.issue_replay.repair_harness import repair_one
                produced, cost, did = repair_one(b, root, model_id=_MODELS[model][0],
                                                 rate=_MODELS[model][1], k=max_steps)
            elif mode == "harness":
                produced, cost, did = _produce_harness(b, model, root, max_steps=max_steps)
            elif mode == "vendor":
                produced, cost, did = _produce_vendor(b, agent, root)
            else:
                produced, cost, did = _produce(b, model, root)
            total_cost += cost
            ran += int(did)
            hidden, public = verify(b, root, module_src=produced)
            probes = _probes_from_tests(b)
            eq = bool(probes) and patch_equivalent(b, produced, probes=probes)
            solved += int(hidden)
            equiv += int(eq)
            by_source[b.source][1] += 1
            by_source[b.source][0] += int(hidden)
            per_bundle.append({"repo": b.repo_name, "module": b.module_path, "source": b.source,
                               "task_type": b.task_type, "hidden_pass": hidden, "public_pass": public,
                               "patch_equivalent": eq, "cost_usd": cost})
            print(f"[{b.repo_name:14}] hidden={hidden} public={public} equiv={eq} "
                  f"${cost:.5f} ({time.time()-t0:.0f}s)", flush=True)
    n = len(bundles)
    p, lo, hi = wilson_ci(solved, n)
    return {
        "experiment": "issue_replay_live",
        "question": "can a live cheap model solve issue->fix replay bundles, judged by held-out hidden tests + patch-equivalence?",
        "model": (agent or model), "agent": agent, "mode": mode,
        "n_bundles": n, "elapsed_s": round(time.time() - t0, 1),
        "hidden_verified": {"solved": solved, "n": n, "rate": round(p, 4), "ci": [round(lo, 4), round(hi, 4)]},
        "patch_equivalent_rate": round(equiv / n, 4) if n else 0.0,
        "ran_live": ran,
        "total_cost_usd": round(total_cost, 6),
        "cost_per_verified_success": round(total_cost / solved, 6) if solved else None,
        "by_source": {s: {"solved": v[0], "n": v[1], "rate": round(v[0] / v[1], 4) if v[1] else 0.0}
                      for s, v in sorted(by_source.items())},
        "per_bundle": per_bundle,
        "evidence_tier": "live single-shot over issue->fix bundles; gold patch + hidden tests withheld; "
                         "bundles labelled by source (frozen_synthetic vs real_issue_replay)",
    }


def _load_bundles(which: str, bundle_file: str = "") -> list[IssueReplayTask]:
    if bundle_file:  # explicit corpus file (e.g. the P4 net-new harder bundles) overrides `which`
        return [IssueReplayTask(**d) for d in json.loads(Path(bundle_file).read_text())]
    bundles: list[IssueReplayTask] = []
    if which in ("synthetic", "all"):
        bundles += frozen_bundles()
    if which in ("real", "all"):
        full = Path("reports/real_issue_replay_full.json")
        if full.exists():
            bundles += [IssueReplayTask(**d) for d in json.loads(full.read_text())]
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini", choices=list(_MODELS))
    ap.add_argument("--bundles", default="synthetic", choices=["synthetic", "real", "all"])
    ap.add_argument("--bundle-file", default="", help="explicit full-bundle JSON to run (overrides --bundles)")
    ap.add_argument("--mode", default="single", choices=["single", "harness", "repair", "vendor"])
    ap.add_argument("--agent", default="claude_code",
                    choices=["claude_code", "codex_cli", "gemini_cli"], help="vendor CLI agent (mode=vendor)")
    ap.add_argument("--max-steps", type=int, default=14, help="harness step budget; in repair mode = best-of-k")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep between bundles (rate-limit throttle)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of bundles (0 = all)")
    ap.add_argument("--out", default="reports/issue_replay_live.json")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    picked = _load_bundles(args.bundles, args.bundle_file)
    if args.limit:
        picked = picked[:args.limit]
    rep = run(args.model, picked, mode=args.mode, max_steps=args.max_steps, delay_s=args.delay,
              agent=args.agent)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    h = rep["hidden_verified"]
    print(f"\n=== ISSUE REPLAY (live, {rep['model']}, mode={args.mode}) ===")
    print(f"hidden-verified {h['solved']}/{h['n']} = {h['rate']:.2f} CI[{h['ci'][0]:.2f},{h['ci'][1]:.2f}]  "
          f"patch-equivalent {rep['patch_equivalent_rate']:.2f}  ${rep['total_cost_usd']:.4f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
