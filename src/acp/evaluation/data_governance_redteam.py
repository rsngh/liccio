"""Data-governance red-team lab (Alpha 11, WS11).

Drives adversarial attempts against the *real* data-governance policies
(:mod:`acp.training.governance` + :mod:`acp.training.repo_boundary`) and asserts
each violation is contained. Unlike the sandbox red-team, every attack here runs
for real against the production policy objects — the policies are pure and
deterministic, so the attempts are safe to execute.

An attack is **blocked** when the policy hard-denies it (training/read denied,
canary not in the train split), and **flagged** when the policy surfaces an
audit failure that must halt promotion (rollback required, memorization leak,
export-before-audit). A leak is any attack that the policies let through
silently; the summary asserts there are none.
"""

from __future__ import annotations

from acp.schemas.training import TrainingExample
from acp.training.governance import (
    DatasetAccessPolicy,
    ModelRollbackPolicy,
    governance_check,
)
from acp.training.repo_boundary import (
    MemorizationCanary,
    RepoDataBoundary,
    RepoHoldoutSplit,
)

# Repos used across the attacks.
_PRIVATE_A = "repo-private-a"
_PRIVATE_B = "repo-private-b"
_PUBLIC = "repo-public"


def _attack_private_into_global() -> dict:
    """A private repo's data tries to enter the *global* training pool."""
    decision = governance_check(
        repo_id=_PRIVATE_A,
        dataset_kind="repair",
        private_repos={_PRIVATE_A},
        allowlist=set(),
        n_examples=1000,
    )
    blocked = not decision["may_train_global"]
    return {
        "status": "blocked" if blocked else "leak",
        "detail": (
            "private repo data blocked from global model: "
            + "; ".join(decision["reasons"])
        ),
    }


def _attack_cross_repo_partition() -> dict:
    """Private repo A's examples try to reach repo B's model via partitioning."""
    examples = [
        TrainingExample(
            dataset_kind="repair",
            task_id=f"a-task-{i}",
            provenance={"repo_id": _PRIVATE_A},
        )
        for i in range(5)
    ]
    boundary = RepoDataBoundary()
    buckets = boundary.partition(
        examples,
        target_repo_id=_PRIVATE_B,
        private_repos={_PRIVATE_A, _PRIVATE_B},
        repo_of={ex.task_id: _PRIVATE_A for ex in examples if ex.task_id},
    )
    leaked_into_b = buckets["target_repo_examples"]
    leaked_into_global = buckets["global_pool_examples"]
    blocked = not leaked_into_b and not leaked_into_global
    return {
        "status": "blocked" if blocked else "leak",
        "detail": (
            f"repo A examples in repo B model: {len(leaked_into_b)}, "
            f"in global pool: {len(leaked_into_global)} (expected 0/0)"
        ),
    }


def _attack_canary_in_training() -> dict:
    """A planted memorization canary tries to slip into the train split."""
    examples = [
        TrainingExample(
            dataset_kind="repair",
            task_id=f"canary-task-{i}",
            inputs={"prompt": f"secret is CANARY-leak{i:04d}"},
            target=f"CANARY-leak{i:04d}",
        )
        for i in range(40)
    ]
    splitter = RepoHoldoutSplit(holdout_fraction=0.2)
    split = splitter.split(examples)
    canaries = splitter.holdout_canaries(examples)
    # The attack succeeds (leak) if any held-out canary also appears in train.
    train_blob = "".join(ex.canonical_json() for ex in split["train"])
    leaked = [c for c in canaries if c in train_blob]
    blocked = bool(canaries) and not leaked
    return {
        "status": "blocked" if blocked else "leak",
        "detail": (
            f"{len(canaries)} held-out canaries; {len(leaked)} also in train split "
            "(expected 0; train ∩ holdout = ∅)"
        ),
    }


def _attack_allowlist_bypass() -> dict:
    """A private repo NOT on the allowlist tries to read another's dataset."""
    policy = DatasetAccessPolicy(private_repos={_PRIVATE_A}, allowlist={_PUBLIC})
    reasons = policy.deny_reasons(
        reader_repo_id=_PRIVATE_B,
        owner_repo_id=_PRIVATE_A,
        dataset_kind="repair",
    )
    blocked = bool(reasons)
    return {
        "status": "blocked" if blocked else "leak",
        "detail": (
            "allowlist bypass denied: " + "; ".join(reasons)
            if reasons
            else "non-allowlisted reader was allowed (leak)"
        ),
    }


def _attack_no_rollback_plan() -> dict:
    """A regressing model is promoted without a rollback plan being honored."""
    policy = ModelRollbackPolicy(max_regression=0.05)
    decision = policy.should_rollback(
        baseline_metric=0.80,
        observed_metric=0.60,  # 0.20 regression > 0.05
        safety_violation=False,
        memorization_clean=True,
    )
    flagged = bool(decision["rollback"])
    return {
        "status": "flagged" if flagged else "leak",
        "detail": (
            "model artifact without honored rollback plan flagged: "
            + "; ".join(decision["reasons"])
            if flagged
            else "regression past threshold did not require rollback (leak)"
        ),
    }


def _attack_export_before_audit() -> dict:
    """A dataset export is attempted before the leakage/memorization audit."""
    examples = [
        TrainingExample(
            dataset_kind="repair",
            task_id="leak-task",
            inputs={"prompt": "value CANARY-export9999"},
            target="CANARY-export9999",
        )
    ]
    canary = MemorizationCanary()
    # Simulate "export" = surfacing example content as model output before audit.
    outputs = [ex.canonical_json() for ex in examples]
    audit = canary.audit_model_outputs(outputs, ["CANARY-export9999"])
    # The audit must catch the leak and thereby block the premature export.
    flagged = not audit["clean"]
    return {
        "status": "flagged" if flagged else "leak",
        "detail": (
            f"export-before-audit caught {len(audit['leaked'])} leaked canaries; "
            "export blocked pending leakage audit"
            if flagged
            else "leakage audit passed a known leak (leak)"
        ),
    }


_ATTACKS: dict[str, object] = {
    "private_repo_into_global_training": _attack_private_into_global,
    "repo_a_examples_in_repo_b_model": _attack_cross_repo_partition,
    "memorization_canary_in_training": _attack_canary_in_training,
    "allowlist_bypass": _attack_allowlist_bypass,
    "model_artifact_without_rollback_plan": _attack_no_rollback_plan,
    "dataset_export_before_leakage_audit": _attack_export_before_audit,
}


def run_data_governance_redteam() -> dict:
    """Run every governance attack and assert each is blocked or flagged.

    Returns a per-attack ``{status: blocked|flagged|leak, detail}`` map plus a
    summary ``{n_attacks, all_blocked, leaks}`` where ``all_blocked`` is true
    only when no attack slipped through and ``leaks`` lists any that did.
    """
    attacks: dict[str, dict] = {}
    for name, fn in _ATTACKS.items():
        attacks[name] = fn()  # type: ignore[operator]

    leaks = [name for name, result in attacks.items() if result["status"] == "leak"]
    return {
        "attacks": attacks,
        "summary": {
            "n_attacks": len(attacks),
            "all_blocked": not leaks,
            "leaks": leaks,
        },
    }
