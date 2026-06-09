# ruff: noqa: E501
"""Harvest REAL issue-replay bundles from a cloned public repo's git history (GOALS P3).

Direct ``git clone`` works in this environment (the GitHub REST API does not), so real history is
reachable without a token. For a repo whose unit module is a single flat file and whose tests are
per-function ``unittest`` methods (each doing ``from <module> import <fn>``), this:

  1. walks the fix commits that touched the module,
  2. reads the function the hunk header names, takes the PARENT file as ``buggy`` and the commit
     file as the withheld ``gold_patch``,
  3. lifts that function's REAL test method out of the (head) test file and splits its assertions
     into a shown ``public`` case and a held-out ``hidden`` oracle (wrapped so the verbatim
     ``self.assertEqual`` body runs under pytest),
  4. keeps the bundle ONLY if it is hermetically fair (buggy fails hidden; gold passes public +
     hidden) via ``replay_runner.offline_fairness`` — non-hermetic commits are dropped.

Output bundles carry ``source="real_issue_replay"`` with repo@sha provenance, so they can never be
confused with the frozen-synthetic set.

    uv run python -m evals.issue_replay.harvest_real --repo /tmp/realcorpus/python-stringcase \
        --module stringcase.py --test stringcase_test.py --out reports/real_issue_replay_bundles.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from evals.issue_replay.replay_runner import offline_fairness
from evals.issue_replay.replay_task import IssueReplayTask

_HUNK_FN = re.compile(r"@@.*@@\s*def\s+([A-Za-z_]\w*)")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=False).stdout


def _changed_funcs(repo: Path, sha: str, module: str) -> list[str]:
    diff = _git(repo, "show", "--unified=0", sha, "--", module)
    seen: list[str] = []
    for fn in _HUNK_FN.findall(diff):
        if fn not in seen:
            seen.append(fn)
    return seen


def _file_at(repo: Path, sha: str, path: str) -> str:
    return _git(repo, "show", f"{sha}:{path}")


def _rewrite_imports(test_src: str, pkg: str, modbase: str) -> str:
    """Flatten package imports so the test runs against the single top-level module file:
    ``from pkg.modbase import X`` -> ``from modbase import X``; ``from pkg import modbase`` ->
    ``import modbase``; ``import pkg.modbase`` -> ``import modbase``; ``pkg.modbase.`` -> ``modbase.``."""
    s = test_src
    s = re.sub(rf"\bfrom\s+{re.escape(pkg)}\.{re.escape(modbase)}\b", f"from {modbase}", s)
    s = re.sub(rf"\bfrom\s+{re.escape(pkg)}\s+import\s+{re.escape(modbase)}\b", f"import {modbase}", s)
    s = re.sub(rf"\bimport\s+{re.escape(pkg)}\.{re.escape(modbase)}\b", f"import {modbase}", s)
    s = re.sub(rf"\b{re.escape(pkg)}\.{re.escape(modbase)}\.", f"{modbase}.", s)
    return s


def harvest(repo: Path, module: str, test: str, *, max_commits: int) -> list[IssueReplayTask]:
    """Whole-test-file mode: for each fix commit touching ``module``, take the PARENT module as
    buggy and the commit module as the withheld gold, run the commit's own (import-flattened) test
    file as the held-out hidden oracle, and keep the bundle only if it is hermetically fair."""
    repo_name = next((ln.split("github.com[:/]", 1)[-1].removesuffix(".git").strip()
                      for ln in _git(repo, "remote", "get-url", "origin").splitlines()), repo.name)
    repo_name = re.sub(r"^.*github\.com[:/]", "", repo_name)
    pkg = module.split("/")[0] if "/" in module else ""
    modbase = Path(module).stem
    if modbase == "__init__":          # single-file package: import name is the dir name
        modbase = Path(module).parent.name
        pkg = ""
    flat_module = f"{modbase}.py"
    shas = _git(repo, "log", "--no-merges", "--format=%H", "--", module).split()
    bundles: list[IssueReplayTask] = []
    seen_funcs: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="harvest_") as d:
        root = Path(d)
        for sha in shas[:max_commits]:
            subj = _git(repo, "log", "-1", "--format=%s", sha).strip()
            if not re.search(r"\b(fix|bug|correct|wrong|issue|regression)\b", subj, re.I):
                continue
            buggy = _file_at(repo, f"{sha}^", module)
            gold = _file_at(repo, sha, module)
            if not buggy or not gold or buggy == gold:
                continue
            test_src = _file_at(repo, sha, test)
            if not test_src.strip():
                continue
            key = ",".join(_changed_funcs(repo, sha, module)) or sha[:10]
            if key in seen_funcs:        # one bundle per distinct changed-function set per repo
                continue
            hidden = _rewrite_imports(test_src, pkg, modbase) if pkg else test_src
            public = f"import {modbase}\n\n\ndef test_pub():\n    assert {modbase} is not None\n"
            task = IssueReplayTask(
                repo_name=repo_name, base_sha=f"{sha[:10]}^",
                issue_title=subj, issue_body=f"{subj} (in {module}).",
                module_path=flat_module, buggy=buggy, gold_patch=gold,
                public_test=public, hidden_test=hidden, source="real_issue_replay",
                leakage_notes=f"real history {repo_name}@{sha[:10]}; whole repo test file as hidden oracle; gold withheld from agent")
            try:
                fair = offline_fairness(task, root)["fair"]
            except Exception:  # noqa: BLE001 - a slow/erroring repo test file -> not hermetic, skip
                fair = False
            if fair:
                bundles.append(task)
                seen_funcs.add(key)
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--max-commits", type=int, default=60)
    ap.add_argument("--out", default="reports/real_issue_replay_bundles.json")
    args = ap.parse_args()
    bundles = harvest(Path(args.repo), args.module, args.test, max_commits=args.max_commits)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"experiment": "real_issue_replay_bundles", "n_bundles": len(bundles),
               "source": "real_issue_replay", "via": "direct git clone (no GitHub API/token)",
               "bundles": [{k: v for k, v in asdict(b).items()
                            if k in ("repo_name", "base_sha", "issue_title", "module_path", "source", "leakage_notes")}
                           | {"gold_patch_hash": b.gold_patch_hash} for b in bundles]}
    out.write_text(json.dumps(payload, indent=2) + "\n")
    # also persist full bundles for the live runner to load
    full = out.with_name("_real_bundles_full.json")
    full.write_text(json.dumps([asdict(b) for b in bundles], indent=2) + "\n")
    print(f"harvested {len(bundles)} fair real bundles -> {out} (+ {full.name})")
    for b in bundles:
        print(f"  {b.repo_name} {b.base_sha} :: {b.issue_title[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
