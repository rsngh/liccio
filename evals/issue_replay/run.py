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


def _adapter(model: str):
    if model == "gemini":
        from acp.agents.gemini_agent import GeminiAgentAdapter
        return GeminiAgentAdapter(name="gemini", model="gemini-3-flash-preview", thinking_budget=0)
    from acp.agents.claude_agent import ClaudeAgentAdapter
    return ClaudeAgentAdapter(name="haiku", model="claude-haiku-4-5")


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
    (src / task.module_path).write_text(task.buggy)
    for p, c in task.extra_files.items():
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
    # cheap-tier cost estimate (haiku $1/$5, gemini-flash ~$0.30/$2.50 per Mtok)
    rate_in, rate_out = (0.30e-6, 2.50e-6) if model == "gemini" else (1e-6, 5e-6)
    cost = round((res.input_token_count or 0) * rate_in + (res.output_token_count or 0) * rate_out, 6)
    return out, cost, True


def run(model: str, bundles: list[IssueReplayTask]) -> dict:
    solved = equiv = ran = 0
    total_cost = 0.0
    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])   # [solved, n]
    per_bundle = []
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="issue_replay_live_") as d:
        root = Path(d)
        for b in bundles:
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
        "model": model, "n_bundles": n, "elapsed_s": round(time.time() - t0, 1),
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini", choices=["gemini", "haiku"])
    ap.add_argument("--out", default="reports/issue_replay_live.json")
    args = ap.parse_args()
    if os.environ.get("ANTHROPIC_API_KEY"):
        os.environ.setdefault("ACP_ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    rep = run(args.model, frozen_bundles())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rep, indent=2)
    for key in ("ANTHROPIC_API_KEY", "ACP_ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        v = os.environ.get(key)
        assert not (v and v in txt), f"{key} leaked"
    out.write_text(txt + "\n")
    h = rep["hidden_verified"]
    print(f"\n=== ISSUE REPLAY (live, {args.model}) ===")
    print(f"hidden-verified {h['solved']}/{h['n']} = {h['rate']:.2f} CI[{h['ci'][0]:.2f},{h['ci'][1]:.2f}]  "
          f"patch-equivalent {rep['patch_equivalent_rate']:.2f}  ${rep['total_cost_usd']:.4f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
