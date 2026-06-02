"""Tests for model & data governance policy objects (Alpha-10 WS19)."""

from __future__ import annotations

from acp.training.governance import (
    DatasetAccessPolicy,
    ModelRollbackPolicy,
    ModelTrainingPermission,
    governance_check,
)


def test_governance_blocks_global_for_private_repo_allows_repo_local() -> None:
    res = governance_check(
        repo_id="private-1",
        dataset_kind="patch",
        private_repos={"private-1"},
        allowlist=set(),
    )
    assert res["may_train_global"] is False
    assert res["may_train_repo_local"] is True
    assert any("allowlist" in r for r in res["reasons"])


def test_allowlisting_permits_global() -> None:
    res = governance_check(
        repo_id="private-1",
        dataset_kind="patch",
        private_repos={"private-1"},
        allowlist={"private-1"},
    )
    assert res["may_train_global"] is True
    assert res["may_train_repo_local"] is True


def test_public_repo_trains_global() -> None:
    res = governance_check(
        repo_id="public-1",
        dataset_kind="patch",
        private_repos=set(),
        allowlist=set(),
    )
    assert res["may_train_global"] is True


def test_insufficient_examples_blocks_repo_local() -> None:
    perm = ModelTrainingPermission()
    res = perm.evaluate(
        repo_id="public-1",
        dataset_kind="patch",
        n_examples=1,
        private_repos=set(),
        allowlist=set(),
    )
    assert res["may_train_repo_local"] is False
    assert res["may_train_global"] is False


def test_rollback_policy_records_plan() -> None:
    plan = ModelRollbackPolicy().record_plan(
        model_run_id="mr-2", rollback_to="mr-1"
    )
    assert plan.model_run_id == "mr-2"
    assert plan.rollback_to == "mr-1"
    assert plan.steps
    assert "rollback_to" in plan.as_dict()


def test_rollback_policy_triggers_on_regression() -> None:
    pol = ModelRollbackPolicy(max_regression=0.05)
    assert pol.should_rollback(baseline_metric=0.8, observed_metric=0.6)["rollback"] is True
    assert pol.should_rollback(baseline_metric=0.8, observed_metric=0.79)["rollback"] is False
    assert pol.should_rollback(
        baseline_metric=0.8, observed_metric=0.8, memorization_clean=False
    )["rollback"] is True


def test_dataset_access_denies_cross_repo_private() -> None:
    pol = DatasetAccessPolicy(private_repos={"private-1"})
    # Cross-repo read of a private repo's dataset is denied.
    assert pol.may_read(
        reader_repo_id="other", owner_repo_id="private-1", dataset_kind="patch"
    ) is False
    # The owning repo may read its own dataset.
    assert pol.may_read(
        reader_repo_id="private-1", owner_repo_id="private-1", dataset_kind="patch"
    ) is True
    # Allowlisted reader is permitted.
    pol2 = DatasetAccessPolicy(private_repos={"private-1"}, allowlist={"other"})
    assert pol2.may_read(
        reader_repo_id="other", owner_repo_id="private-1", dataset_kind="patch"
    ) is True
    # A public repo's dataset is readable cross-repo.
    assert pol.may_read(
        reader_repo_id="other", owner_repo_id="public-1", dataset_kind="patch"
    ) is True
