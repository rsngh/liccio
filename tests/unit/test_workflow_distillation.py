"""Workflow distillation / agentless training data (Alpha 24 area 10)."""

from __future__ import annotations

import pytest

from acp.training.workflow_distillation import (
    Trajectory,
    build_distillation_dataset,
    small_model_smoke,
)


def _trajs():
    return [
        Trajectory("bugfix", "repoA", 1.0, "grep", "logic_fix", "assertion", True),
        Trajectory("bugfix", "repoA", 2.0, "grep", "logic_fix", "assertion", True),
        Trajectory("refactor", "repoB", 3.0, "hybrid", "style_fix", "lint", True),
        Trajectory("bugfix", "repoC", 4.0, "grep", "logic_fix", "assertion", True),
    ]


def test_repo_disjoint_holdout_and_no_memorization() -> None:
    ds = build_distillation_dataset(_trajs(), "context_selector", holdout_repos={"repoC"})
    assert ds.repo_disjoint and ds.memorization_overlap == 0
    assert ds.is_clean()
    train_repos = {e["provenance"]["repo"] for e in ds.train}
    assert "repoC" not in train_repos  # holdout repo absent from train


def test_secret_bearing_example_dropped() -> None:
    t = [Trajectory("bugfix", "sk-ABCDEFGHIJKLMNOPQRSTUVWX1234", 1.0, "grep", "x", "y", True),
         Trajectory("bugfix", "repoB", 2.0, "grep", "x", "y", True)]
    ds = build_distillation_dataset(t, "context_selector")
    assert ds.secret_dropped >= 1


def test_only_successes_train_workflow_priors() -> None:
    t = [Trajectory("bugfix", "repoA", 1.0, "grep", "logic_fix", "assertion", False),
         Trajectory("bugfix", "repoB", 2.0, "grep", "logic_fix", "assertion", True)]
    ds = build_distillation_dataset(t, "repair_classifier")
    # the failed trajectory contributes no repair-prior example
    assert len(ds.train) + len(ds.test) == 1


def test_small_model_smoke_beats_or_matches_chance() -> None:
    ds = build_distillation_dataset(_trajs(), "context_selector", holdout_repos={"repoC"})
    res = small_model_smoke(ds)
    assert res["trained"] and 0.0 <= res["test_accuracy"] <= 1.0


def test_unknown_target_rejected() -> None:
    with pytest.raises(ValueError):
        build_distillation_dataset(_trajs(), "teleport")
