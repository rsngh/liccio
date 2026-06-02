"""Model & data governance policy objects (Alpha-10 WS19).

Builds policy objects *on top of* the Alpha-8 repo-boundary primitives
(:class:`~acp.training.repo_boundary.RepoDataBoundary`,
:class:`~acp.training.repo_boundary.RepoTrainingPolicy`) to answer three
governance questions deterministically:

* **Who/what may read a dataset?** :class:`DatasetAccessPolicy` gates read
  access by dataset kind and repo privacy: a private repo's dataset may only be
  read by that repo (or an explicit allowlist), never cross-repo.
* **What may train a global vs repo-local model?** :class:`ModelTrainingPermission`
  composes the repo boundary + training policy so private-repo data never enters
  the *global* model without an explicit allowlist, while repo-local training
  stays permitted.
* **When/how may a model be rolled back?** :class:`ModelRollbackPolicy` records a
  rollback plan and decides whether a rollback is warranted from observed signals.

The module-level :func:`governance_check` is the one-call summary enforcing the
core invariant: *no private-repo data enters global datasets without an explicit
allowlist.* Everything is pure and deterministic (no network / RNG / keys).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acp.training.repo_boundary import RepoTrainingPolicy

# The core data-governance invariant, surfaced in reasons for auditability.
_GLOBAL_INVARIANT = (
    "no private-repo data enters global datasets without an explicit allowlist"
)


@dataclass
class DatasetAccessPolicy:
    """Gate read access to a dataset by repo privacy and (optional) kind.

    A dataset built from a private repo may be read only by that owning repo, or
    by a repo explicitly named in ``allowlist``. Public datasets are readable by
    anyone. ``restricted_kinds`` optionally narrows the policy to specific
    dataset kinds (when empty, the policy applies to every kind).
    """

    private_repos: set[str] = field(default_factory=set)
    allowlist: set[str] = field(default_factory=set)
    restricted_kinds: set[str] = field(default_factory=set)

    def may_read(
        self,
        *,
        reader_repo_id: str,
        owner_repo_id: str,
        dataset_kind: str,
    ) -> bool:
        """Return whether ``reader_repo_id`` may read ``owner_repo_id``'s dataset."""
        return not self.deny_reasons(
            reader_repo_id=reader_repo_id,
            owner_repo_id=owner_repo_id,
            dataset_kind=dataset_kind,
        )

    def deny_reasons(
        self,
        *,
        reader_repo_id: str,
        owner_repo_id: str,
        dataset_kind: str,
    ) -> list[str]:
        """Reasons (if any) access is denied; empty list means access allowed."""
        reasons: list[str] = []
        # A repo may always read its own dataset.
        if reader_repo_id == owner_repo_id:
            return reasons
        if self.restricted_kinds and dataset_kind not in self.restricted_kinds:
            return reasons
        owner_private = owner_repo_id in self.private_repos
        reader_allowed = reader_repo_id in self.allowlist
        if owner_private and not reader_allowed:
            reasons.append(
                f"reader {reader_repo_id} may not read private repo "
                f"{owner_repo_id}'s {dataset_kind} dataset (not allowlisted)"
            )
        return reasons


@dataclass
class ModelTrainingPermission:
    """Decide whether a (repo, dataset_kind) may train global vs repo-local.

    Composes :class:`~acp.training.repo_boundary.RepoTrainingPolicy`: repo-local
    training is permitted whenever the repo has enough examples; global training
    is permitted only when the repo is non-private or explicitly allowlisted.
    """

    policy: RepoTrainingPolicy = field(default_factory=RepoTrainingPolicy)

    def evaluate(
        self,
        *,
        repo_id: str,
        dataset_kind: str,
        n_examples: int,
        private_repos: set[str],
        allowlist: set[str],
    ) -> dict:
        is_private = repo_id in private_repos
        allowlisted = repo_id in allowlist
        eligibility = self.policy.evaluate(
            repo_id=repo_id,
            dataset_kind=dataset_kind,
            n_examples=n_examples,
            is_private=is_private,
            allowlisted=allowlisted,
        )
        reasons = list(eligibility.reasons)
        may_train_repo_local = eligibility.repo_specific_eligible
        may_train_global = (
            eligibility.repo_specific_eligible
            and eligibility.global_contribution_allowed
        )
        if is_private and not allowlisted:
            reasons.append(_GLOBAL_INVARIANT)
        return {
            "repo_id": repo_id,
            "dataset_kind": dataset_kind,
            "is_private": is_private,
            "allowlisted": allowlisted,
            "may_train_global": may_train_global,
            "may_train_repo_local": may_train_repo_local,
            "reasons": reasons,
        }


@dataclass
class ModelRollbackPlan:
    """An immutable record describing how to roll a model back."""

    model_run_id: str
    rollback_to: str
    trigger: str
    steps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "model_run_id": self.model_run_id,
            "rollback_to": self.rollback_to,
            "trigger": self.trigger,
            "steps": self.steps,
        }


@dataclass
class ModelRollbackPolicy:
    """Conditions under which a promoted model must be rolled back.

    A rollback is warranted when an observed regression on a tracked metric
    exceeds ``max_regression`` (e.g. solve rate dropping), when a safety
    violation is observed, or when a memorization/leak audit fails. Every
    promoted model must carry a :class:`ModelRollbackPlan`.
    """

    max_regression: float = 0.05

    def record_plan(
        self,
        *,
        model_run_id: str,
        rollback_to: str,
        trigger: str = "regression or safety violation",
    ) -> ModelRollbackPlan:
        """Create the rollback plan record shipped alongside a promotion."""
        return ModelRollbackPlan(
            model_run_id=model_run_id,
            rollback_to=rollback_to,
            trigger=trigger,
            steps=[
                f"freeze routing to {model_run_id}",
                f"repoint serving to {rollback_to}",
                "open incident + audit the regression",
            ],
        )

    def should_rollback(
        self,
        *,
        baseline_metric: float,
        observed_metric: float,
        safety_violation: bool = False,
        memorization_clean: bool = True,
    ) -> dict:
        """Decide whether a rollback is warranted from observed signals."""
        reasons: list[str] = []
        regression = baseline_metric - observed_metric
        if regression > self.max_regression:
            reasons.append(
                f"metric regressed {regression:.3f} > {self.max_regression}"
            )
        if safety_violation:
            reasons.append("safety violation observed in production")
        if not memorization_clean:
            reasons.append("memorization/leak audit failed")
        return {"rollback": bool(reasons), "reasons": reasons}


def governance_check(
    *,
    repo_id: str,
    dataset_kind: str,
    private_repos: set[str],
    allowlist: set[str],
    n_examples: int = 1_000_000,
) -> dict:
    """One-call governance summary for a (repo, dataset_kind).

    Enforces the core invariant — *no private-repo data enters global datasets
    without an explicit allowlist* — returning::

        {may_train_global, may_train_repo_local, reasons}

    ``n_examples`` defaults high so the check reflects the *privacy* gate (not
    the example-count gate) unless a caller passes a real count.
    """
    permission = ModelTrainingPermission()
    decision = permission.evaluate(
        repo_id=repo_id,
        dataset_kind=dataset_kind,
        n_examples=n_examples,
        private_repos=private_repos,
        allowlist=allowlist,
    )
    return {
        "may_train_global": decision["may_train_global"],
        "may_train_repo_local": decision["may_train_repo_local"],
        "reasons": decision["reasons"],
    }
