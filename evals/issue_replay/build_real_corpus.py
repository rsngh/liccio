# ruff: noqa: E501
"""Build a REAL issue-replay corpus by cloning public repos and harvesting fix commits (GOALS P3).

Reproducible driver over :func:`harvest_real.harvest`: clones each repo (direct ``git clone`` — no
GitHub token/API needed, which is what is actually reachable here), harvests hermetically-fair real
bundles from its fix commits, and accumulates them into one corpus + provenance manifest.

    uv run python -m evals.issue_replay.build_real_corpus --out reports/real_issue_replay_bundles.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from evals.issue_replay.harvest_real import harvest

# (repo_url, [(module_path_in_repo, test_path_in_repo), ...]); flat single-file modules with a
# co-located test file. Modules that yield no hermetically-fair bundle are simply skipped.
REPOS: list[tuple[str, list[tuple[str, str]]]] = [
    ("https://github.com/okunishinishi/python-stringcase",
     [("stringcase.py", "stringcase_test.py")]),
    ("https://github.com/mahmoud/boltons",
     [(f"boltons/{m}.py", f"tests/test_{m}.py") for m in
      ("strutils", "dictutils", "cacheutils", "timeutils", "setutils", "listutils",
       "iterutils", "mathutils", "funcutils", "formatutils", "fileutils", "jsonutils",
       "statsutils", "queueutils", "tableutils", "namedutils", "ioutils")]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-commits", type=int, default=120)
    ap.add_argument("--out", default="reports/real_issue_replay_bundles.json")
    args = ap.parse_args()
    all_bundles = []
    with tempfile.TemporaryDirectory(prefix="real_corpus_") as d:
        cache = Path(d)
        for url, modules in REPOS:
            dest = cache / url.rstrip("/").split("/")[-1]
            print(f"cloning {url} ...", flush=True)
            subprocess.run(["git", "clone", "--quiet", "--depth", "400", url, str(dest)],
                           check=False, env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin"})
            for module, test in modules:
                if not (dest / test).exists():
                    continue
                got = harvest(dest, module, test, max_commits=args.max_commits)
                for b in got:
                    print(f"  + {b.repo_name} {b.base_sha} :: {b.issue_title[:64]}", flush=True)
                all_bundles += got
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "experiment": "real_issue_replay_bundles",
        "n_bundles": len(all_bundles),
        "source": "real_issue_replay",
        "via": "direct git clone of public repos (no GitHub API/token; api.github.com is proxy-blocked here)",
        "repos": sorted({b.repo_name for b in all_bundles}),
        "fairness": "each bundle validated offline-fair (buggy fails the repo's own test file; gold passes)",
        "bundles": [{k: v for k, v in asdict(b).items()
                     if k in ("repo_name", "base_sha", "issue_title", "module_path", "source", "leakage_notes")}
                    | {"gold_patch_hash": b.gold_patch_hash} for b in all_bundles],
    }
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    full = out.with_name("real_issue_replay_full.json")
    full.write_text(json.dumps([asdict(b) for b in all_bundles], indent=2) + "\n")
    print(f"\nbuilt {len(all_bundles)} real bundles across {len(manifest['repos'])} repos -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
