"""Two small corpora for the harness arena (CLIs are slow → keep tight).

capability: well-specified, self-contained bugfixes — harness-overkill control (single-shot already
            solves these, so a harness should match, not beat).
ceiling:    cross-file tasks where the answer lives in an unreferenced file — single-shot scores 0
            (can't see it); an autonomous harness must explore the repo to find it.
"""

from __future__ import annotations

from evals.hetero_arena.tier_tasks import all_capability_tasks
from evals.metarouter_arena.schema import ArenaTaskSpec

_CAP_NAMES = {"cap_reverse", "cap_roman", "cap_editdist", "cap_calc_unary",
              "cap_simplify_path", "cap_min_coins"}


def capability_corpus() -> list[ArenaTaskSpec]:
    return [t for t in all_capability_tasks() if t.name in _CAP_NAMES]


def ceiling_corpus(limit: int = 8) -> list[ArenaTaskSpec]:
    from evals.hard_realism_arena.task_pack import load_hard_tasks
    gated = [t for t in load_hard_tasks()
             if t.context_need in ("cross_file_api", "broad_repo_map") and not t.forbidden_files]
    return gated[:limit]


def corpus(name: str) -> list[ArenaTaskSpec]:
    if name == "capability":
        return capability_corpus()
    if name == "ceiling":
        return ceiling_corpus()
    raise SystemExit(f"unknown corpus {name}")
