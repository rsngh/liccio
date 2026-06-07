"""Issue-replay framework tests (GOALS Alpha 44 P1)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from evals.issue_replay.replay_runner import offline_fairness, patch_equivalent
from evals.issue_replay.replay_task import frozen_bundles


def test_all_frozen_bundles_offline_fair() -> None:
    bundles = frozen_bundles()
    assert len(bundles) >= 6
    with tempfile.TemporaryDirectory() as d:
        for b in bundles:
            f = offline_fairness(b, Path(d))
            assert f["fair"], (b.repo_name, f)


def test_bundles_labeled_synthetic_not_real() -> None:
    # honesty: no bundle may claim the real_issue_replay tier in this network-free environment
    assert all(b.source == "frozen_synthetic" for b in frozen_bundles())


def test_patch_equivalence_judge() -> None:
    b = next(x for x in frozen_bundles() if x.module_path == "dates.py")
    probes = ["m.offset_minutes('x+05:00')", "m.offset_minutes('xZ')"]
    assert patch_equivalent(b, b.gold_patch, probes=probes)         # gold == gold
    assert not patch_equivalent(b, b.buggy, probes=probes)          # buggy != gold


def test_gold_patch_hash_stable() -> None:
    b = frozen_bundles()[0]
    assert len(b.gold_patch_hash) == 16 and b.gold_patch_hash == frozen_bundles()[0].gold_patch_hash
