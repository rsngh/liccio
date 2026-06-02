"""Repo-specific training & memory-boundary enforcement (Alpha 8, WS19).

A repo-specific model is fine-tuned to improve one repository / task type. It
must respect a hard data boundary:

* **Private repos stay private.** A private repo's examples contribute *only*
  to that repo's own repo-specific dataset and never to the shared global pool,
  unless the repo is explicitly allowlisted into the global pool.
* **Held-out secret canaries must not leak.** A deterministic holdout split
  reserves examples (carrying planted ``CANARY-...`` tokens) that the model
  never trains on; a memorization audit then verifies the model cannot
  reproduce any held-out canary.
* **Eligibility is policy-gated.** A (repo, dataset_kind) pair is only eligible
  for repo-specific training with enough examples, and may only contribute to
  the global model when it is not private or has been allowlisted.

Everything here is pure and deterministic (stable hashing via :mod:`hashlib`),
so partitions and splits reproduce exactly across processes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from acp.schemas.training import TrainingExample
from acp.training.model_governance import MemorizationAudit

# A planted secret canary token, e.g. ``CANARY-7f3a9c2b`` or ``CANARY-abc123``.
CANARY_PATTERN: re.Pattern[str] = re.compile(r"CANARY-[A-Za-z0-9_\-]+")


def _stable_fraction(key: str) -> float:
    """Map an arbitrary key to a deterministic fraction in ``[0, 1)``.

    Uses a stable SHA-256 digest so splits reproduce across processes (no RNG /
    hash-seed pitfalls).
    """
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(1 << 64)


@dataclass
class RepoDataBoundary:
    """Partition training examples by repo while enforcing privacy.

    Private repos contribute only to their own repo-specific set; they reach the
    global pool only when allowlisted. Examples whose repo cannot be resolved are
    treated as global (they carry no private-repo association).
    """

    def partition(
        self,
        examples: list[TrainingExample],
        target_repo_id: str,
        *,
        private_repos: set[str],
        allowlist: set[str] = frozenset(),  # type: ignore[assignment]
        repo_of: dict[str, str | None] | None = None,
    ) -> dict[str, list[TrainingExample]]:
        """Split ``examples`` into target-repo and global-pool buckets.

        ``repo_of`` maps ``task_id`` -> ``repo_id``; when omitted, an example's
        repo is read from ``provenance['repo_id']``. An example contributes to
        the global pool unless its repo is private and not allowlisted.
        """
        target: list[TrainingExample] = []
        global_pool: list[TrainingExample] = []
        for ex in examples:
            repo = self._repo_for(ex, repo_of)
            if repo == target_repo_id:
                target.append(ex)
            is_private = repo is not None and repo in private_repos
            allowed = repo is not None and repo in allowlist
            if not is_private or allowed:
                global_pool.append(ex)
        return {
            "target_repo_examples": target,
            "global_pool_examples": global_pool,
        }

    @staticmethod
    def _repo_for(
        ex: TrainingExample, repo_of: dict[str, str | None] | None
    ) -> str | None:
        if repo_of is not None and ex.task_id is not None:
            return repo_of.get(ex.task_id)
        repo = ex.provenance.get("repo_id")
        return repo if isinstance(repo, str) else None


@dataclass
class RepoHoldoutSplit:
    """Deterministic train/holdout split of a single repo's examples.

    The split is keyed on a stable hash of ``task_id`` (falling back to the
    example id), so it is reproducible and train ∩ holdout = ∅.
    """

    holdout_fraction: float = 0.2

    def split(
        self, examples: list[TrainingExample]
    ) -> dict[str, list[TrainingExample]]:
        train: list[TrainingExample] = []
        holdout: list[TrainingExample] = []
        for ex in examples:
            key = ex.task_id or ex.id
            if _stable_fraction(key) < self.holdout_fraction:
                holdout.append(ex)
            else:
                train.append(ex)
        return {"train": train, "holdout": holdout}

    def holdout_canaries(self, examples: list[TrainingExample]) -> list[str]:
        """Extract planted ``CANARY-...`` tokens from the holdout examples.

        Returns the sorted, de-duplicated set of canary tokens found in the
        holdout split's content (inputs + target), ready for the memorization
        audit.
        """
        holdout = self.split(examples)["holdout"]
        found: set[str] = set()
        for ex in holdout:
            blob = ex.canonical_json()
            found.update(CANARY_PATTERN.findall(blob))
        return sorted(found)


@dataclass
class MemorizationCanary:
    """Thin wrapper over :class:`MemorizationAudit` for held-out canaries."""

    def audit_model_outputs(
        self, outputs: list[str], canaries: list[str]
    ) -> dict:
        """Assert no held-out canary appears in model ``outputs``.

        Returns the audit dict from :class:`MemorizationAudit` (``clean`` is
        ``True`` only when no canary leaked).
        """
        return MemorizationAudit(canaries=list(canaries)).audit(outputs)


@dataclass
class RepoTrainingEligibility:
    """Decision for whether a (repo, dataset_kind) may be trained / globalized."""

    repo_id: str
    dataset_kind: str
    n_examples: int
    repo_specific_eligible: bool
    global_contribution_allowed: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "repo_id": self.repo_id,
            "dataset_kind": self.dataset_kind,
            "n_examples": self.n_examples,
            "repo_specific_eligible": self.repo_specific_eligible,
            "global_contribution_allowed": self.global_contribution_allowed,
            "reasons": self.reasons,
        }


@dataclass
class RepoTrainingPolicy:
    """Gates repo-specific training and global contribution by repo privacy."""

    min_examples: int = 10

    def evaluate(
        self,
        *,
        repo_id: str,
        dataset_kind: str,
        n_examples: int,
        is_private: bool,
        allowlisted: bool = False,
    ) -> RepoTrainingEligibility:
        reasons: list[str] = []
        repo_eligible = n_examples >= self.min_examples
        if not repo_eligible:
            reasons.append(
                f"insufficient examples: {n_examples} < {self.min_examples}"
            )
        global_allowed = (not is_private) or allowlisted
        if is_private and not allowlisted:
            reasons.append(
                f"repo {repo_id} is private and not allowlisted: "
                "blocked from global model"
            )
        if not reasons:
            reasons.append("eligible for repo-specific training and global pool")
        return RepoTrainingEligibility(
            repo_id=repo_id,
            dataset_kind=dataset_kind,
            n_examples=n_examples,
            repo_specific_eligible=repo_eligible,
            global_contribution_allowed=global_allowed,
            reasons=reasons,
        )
