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
    # harder, algorithmically richer flat-module libs added in P4 to break the 17/17 ceiling and
    # produce bundles that actually SEPARATE the agents (toolz = functional/currying edge cases;
    # parse = format-string parsing). Same `from pkg.module import fn` pattern the harvester flattens.
    ("https://github.com/pytoolz/toolz",
     [(f"toolz/{m}.py", f"toolz/tests/test_{m}.py") for m in
      ("itertoolz", "functoolz", "dicttoolz", "recipes")]),
    ("https://github.com/r1chardj0n3s/parse",
     [("parse.py", "tests/test_parse.py"), ("parse.py", "tests/test_bugs.py"),
      ("parse.py", "tests/test_pattern.py"), ("parse.py", "tests/test_search.py")]),
]
# repos whose tests import sibling submodules -> harvest as package bundles (real package laid down)
PACKAGE_REPOS = {"https://github.com/pytoolz/toolz"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-commits", type=int, default=120)
    ap.add_argument("--only", default="", help="only build repos whose URL contains this substring (comma-separated)")
    ap.add_argument("--out", default="reports/real_issue_replay_bundles.json")
    args = ap.parse_args()
    repos = REPOS
    if args.only:
        subs = [s.strip() for s in args.only.split(",") if s.strip()]
        repos = [(u, m) for u, m in REPOS if any(s in u for s in subs)]
    all_bundles = []
    with tempfile.TemporaryDirectory(prefix="real_corpus_") as d:
        cache = Path(d)
        for url, modules in repos:
            dest = cache / url.rstrip("/").split("/")[-1]
            print(f"cloning {url} ...", flush=True)
            subprocess.run(["git", "clone", "--quiet", "--depth", "400", url, str(dest)],
                           check=False, env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin"})
            pkg_mode = url in PACKAGE_REPOS  # tests import sibling submodules -> lay down the real package
            for module, test in modules:
                if not (dest / test).exists():
                    continue
                got = harvest(dest, module, test, max_commits=args.max_commits, package_mode=pkg_mode)
                for b in got:
                    print(f"  + {b.repo_name} {b.base_sha} :: {b.issue_title[:64]}", flush=True)
                all_bundles += got
    # dedupe identical fixes harvested via >1 test file (same repo+commit+gold = one bundle)
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for b in all_bundles:
        key = (b.repo_name, b.base_sha, b.gold_patch_hash)
        if key not in seen:
            seen.add(key)
            deduped.append(b)
    all_bundles = deduped
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
    # full-bundle file tracks --out (…bundles[_x].json -> …full[_x].json) so a custom --out never
    # clobbers the canonical v1 corpus reports/real_issue_replay_full.json
    full = out.with_name(out.name.replace("bundles", "full")) if "bundles" in out.name \
        else out.with_name(out.stem + "_full.json")
    full.write_text(json.dumps([asdict(b) for b in all_bundles], indent=2) + "\n")
    print(f"\nbuilt {len(all_bundles)} real bundles across {len(manifest['repos'])} repos -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
