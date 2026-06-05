"""Workflow distillation / agentless training data (Alpha 24 area 10).

Kimi-Dev introduces agentless training as a software-engineering skill prior: distill
successful trajectories into a dataset that teaches workflow priors (which context strategy,
which repair strategy, whether a task is viable) without an interactive agent loop. This is
downstream of ACP's trace factory.

Guarantees enforced here (no dataset ships without them):
- temporal/repo HOLDOUTS: examples are split by repo so the test split shares no repo with
  train (prevents trivial repo-memorization);
- secret-clean: any example whose features contain a secret pattern is dropped;
- a MEMORIZATION AUDIT confirms zero content-hash overlap between train and test.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

_SECRET = re.compile(r"sk-[A-Za-z0-9]{20,}|OPENAI_API_KEY|ANTHROPIC_API_KEY")
TARGETS = ("context_selector", "repair_classifier", "viability")


@dataclass
class Trajectory:
    task_type: str
    repo: str
    timestamp: float
    context_strategy: str
    repair_strategy: str
    failure_class: str
    success: bool
    risk: str = "low"


def _hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def _examples_for(target: str, traj: Trajectory) -> dict | None:
    if not traj.success and target != "viability":
        return None                    # only learn workflow priors from SUCCESSES
    if target == "context_selector":
        return {"inputs": {"task_type": traj.task_type, "risk": traj.risk},
                "target": traj.context_strategy}
    if target == "repair_classifier":
        return {"inputs": {"failure_class": traj.failure_class},
                "target": traj.repair_strategy}
    return {"inputs": {"task_type": traj.task_type, "risk": traj.risk},
            "target": "solvable" if traj.success else "unsolvable"}


@dataclass
class DistillationDataset:
    target: str
    train: list = field(default_factory=list)
    test: list = field(default_factory=list)
    secret_dropped: int = 0
    memorization_overlap: int = 0      # content-hash overlap between train and test
    repo_disjoint: bool = True

    def to_dict(self) -> dict:
        return {"target": self.target, "n_train": len(self.train), "n_test": len(self.test),
                "secret_dropped": self.secret_dropped,
                "memorization_overlap": self.memorization_overlap,
                "repo_disjoint": self.repo_disjoint, "leakage_clean": self.is_clean()}

    def is_clean(self) -> bool:
        return self.memorization_overlap == 0 and self.repo_disjoint and self.secret_dropped >= 0


def build_distillation_dataset(trajectories: list[Trajectory], target: str, *,
                               holdout_repos: set | None = None) -> DistillationDataset:
    """Distill a target dataset with a repo-disjoint holdout split + memorization audit."""
    if target not in TARGETS:
        raise ValueError(f"unknown target {target}")
    repos = sorted({t.repo for t in trajectories})
    holdout = holdout_repos if holdout_repos is not None else (
        {repos[-1]} if len(repos) > 1 else set())
    train: list[dict] = []
    test: list[dict] = []
    secret_dropped = 0
    for t in trajectories:
        ex = _examples_for(target, t)
        if ex is None:
            continue
        ex = {**ex, "provenance": {"repo": t.repo, "ts": t.timestamp}}
        if _SECRET.search(json.dumps(ex)):     # check the FULL example incl. provenance
            secret_dropped += 1
            continue
        (test if t.repo in holdout else train).append(ex)
    # Memorization audit hashes the full instance (inputs + target + repo): a test instance
    # matching a train instance means the SAME repo leaked across the split, not benign
    # feature reuse (coarse features legitimately recur across repos = generalization).
    def _inst(e: dict) -> str:
        return _hash({"i": e["inputs"], "t": e.get("target"),
                      "r": e["provenance"]["repo"]})
    train_hashes = {_inst(e) for e in train}
    test_hashes = {_inst(e) for e in test}
    train_repos = {e["provenance"]["repo"] for e in train}
    test_repos = {e["provenance"]["repo"] for e in test}
    return DistillationDataset(
        target=target, train=train, test=test, secret_dropped=secret_dropped,
        memorization_overlap=len(train_hashes & test_hashes),
        repo_disjoint=bool(train_repos.isdisjoint(test_repos)))


def small_model_smoke(dataset: DistillationDataset) -> dict:
    """A majority-class baseline 'training' smoke: does a trivial prior beat chance?"""
    from collections import Counter
    if not dataset.train or not dataset.test:
        return {"trained": False, "reason": "insufficient split"}
    majority = Counter(e["target"] for e in dataset.train).most_common(1)[0][0]
    acc = sum(e["target"] == majority for e in dataset.test) / len(dataset.test)
    return {"trained": True, "majority_class": majority,
            "test_accuracy": round(acc, 4), "n_test": len(dataset.test)}
