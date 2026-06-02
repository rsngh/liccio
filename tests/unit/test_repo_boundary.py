"""Tests for repo-specific training & memory boundary (Alpha 8, WS19)."""

from __future__ import annotations

from acp.schemas.training import TrainingExample
from acp.training.repo_boundary import (
    MemorizationCanary,
    RepoDataBoundary,
    RepoHoldoutSplit,
    RepoTrainingPolicy,
)


def _ex(task_id: str, repo_id: str, **inputs: object) -> TrainingExample:
    return TrainingExample(
        dataset_kind="repair",
        task_id=task_id,
        inputs=dict(inputs),
        provenance={"repo_id": repo_id},
    )


def test_private_repo_excluded_from_global_pool_by_default() -> None:
    examples = [
        _ex("t1", "repo_priv"),
        _ex("t2", "repo_priv"),
        _ex("t3", "repo_pub"),
    ]
    out = RepoDataBoundary().partition(
        examples, target_repo_id="repo_priv", private_repos={"repo_priv"}
    )
    target_ids = {e.id for e in out["target_repo_examples"]}
    global_ids = {e.id for e in out["global_pool_examples"]}

    # Private examples are in their own repo-specific set...
    assert {examples[0].id, examples[1].id} == target_ids
    # ...but NOT in the global pool.
    assert examples[0].id not in global_ids
    assert examples[1].id not in global_ids
    # Public repo example reaches the global pool.
    assert examples[2].id in global_ids


def test_allowlist_lets_private_repo_into_global_pool() -> None:
    examples = [_ex("t1", "repo_priv")]
    out = RepoDataBoundary().partition(
        examples,
        target_repo_id="repo_priv",
        private_repos={"repo_priv"},
        allowlist={"repo_priv"},
    )
    global_ids = {e.id for e in out["global_pool_examples"]}
    assert examples[0].id in global_ids


def test_holdout_split_deterministic_and_disjoint() -> None:
    examples = [_ex(f"task-{i}", "repo_pub") for i in range(50)]
    splitter = RepoHoldoutSplit(holdout_fraction=0.3)

    a = splitter.split(examples)
    b = splitter.split(examples)

    train_a = {e.id for e in a["train"]}
    holdout_a = {e.id for e in a["holdout"]}
    train_b = {e.id for e in b["train"]}
    holdout_b = {e.id for e in b["holdout"]}

    # Deterministic.
    assert train_a == train_b
    assert holdout_a == holdout_b
    # Disjoint and exhaustive.
    assert train_a & holdout_a == set()
    assert train_a | holdout_a == {e.id for e in examples}
    # Both non-empty for a reasonable fraction.
    assert holdout_a
    assert train_a


def test_holdout_canaries_extracted() -> None:
    # Plant canaries; rely on the deterministic split to land them in holdout.
    examples = [
        _ex(f"task-{i}", "repo_pub", note=f"value CANARY-{i:04d}xyz")
        for i in range(50)
    ]
    splitter = RepoHoldoutSplit(holdout_fraction=0.3)
    holdout_ids = {e.id for e in splitter.split(examples)["holdout"]}
    canaries = splitter.holdout_canaries(examples)

    assert canaries  # at least one planted canary landed in holdout
    # Every extracted canary corresponds to a holdout example, none from train.
    holdout_notes = {
        e.inputs["note"].split()[-1]
        for e in examples
        if e.id in holdout_ids
    }
    assert set(canaries) == holdout_notes


def test_memorization_canary_flags_and_passes() -> None:
    canaries = ["CANARY-0001xyz", "CANARY-0002xyz"]
    auditor = MemorizationCanary()

    leaked = auditor.audit_model_outputs(
        ["the secret was CANARY-0001xyz haha"], canaries
    )
    assert leaked["clean"] is False
    assert "CANARY-0001xyz" in leaked["leaked"]

    clean = auditor.audit_model_outputs(["a perfectly innocent answer"], canaries)
    assert clean["clean"] is True
    assert clean["leaked"] == []


def test_policy_blocks_global_contribution_for_private_repo() -> None:
    policy = RepoTrainingPolicy(min_examples=10)
    decision = policy.evaluate(
        repo_id="repo_priv",
        dataset_kind="repair",
        n_examples=42,
        is_private=True,
    )
    assert decision.repo_specific_eligible is True
    assert decision.global_contribution_allowed is False

    allowed = policy.evaluate(
        repo_id="repo_priv",
        dataset_kind="repair",
        n_examples=42,
        is_private=True,
        allowlisted=True,
    )
    assert allowed.global_contribution_allowed is True

    too_few = policy.evaluate(
        repo_id="repo_pub",
        dataset_kind="repair",
        n_examples=3,
        is_private=False,
    )
    assert too_few.repo_specific_eligible is False
    assert too_few.global_contribution_allowed is True
