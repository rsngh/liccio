"""Guarded execution ladder (Alpha 30): move beyond recommend-only, safely.

Shadow mode recommends but never acts. The guarded ladder is the next step: it lets ACP
produce a DRAFT patch / DRAFT PR — actual generated changes, verified in an isolated sandbox
— but with a hard invariant that nothing is applied to a real working tree or merged without
explicit human approval. The execution mode requested for a task is CAPPED by a guardrail
policy: low-risk autonomous PRs are disabled by default, and any write-class mode requires a
sandbox, trusted measurement, a known verifier, a policy dossier, and a rollback plan.

Modes, weakest -> strongest:
    shadow_only -> draft_patch -> draft_pr -> human_approved_apply ->
    human_approved_merge -> low_risk_autonomous_pr
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ExecutionMode(str, Enum):
    SHADOW_ONLY = "shadow_only"
    DRAFT_PATCH = "draft_patch"
    DRAFT_PR = "draft_pr"
    HUMAN_APPROVED_APPLY = "human_approved_apply"
    HUMAN_APPROVED_MERGE = "human_approved_merge"
    LOW_RISK_AUTONOMOUS_PR = "low_risk_autonomous_pr"


_LADDER = list(ExecutionMode)
MODE_RANK = {m: i for i, m in enumerate(_LADDER)}
# modes at/above this rank actually WRITE (apply/merge); below are draft/recommend only.
_WRITE_FLOOR = MODE_RANK[ExecutionMode.HUMAN_APPROVED_APPLY]


@dataclass
class GuardrailPolicy:
    allow_autonomous_pr: bool = False          # low_risk_autonomous_pr off by default
    max_autonomous_risk: str = "low"
    require_sandbox: bool = True
    require_trusted_measurement: bool = True
    require_known_verifier: bool = True


@dataclass
class GuardedDecision:
    task_id: str
    requested_mode: str
    allowed_mode: str
    capped: bool
    autonomous_write: bool                     # True only for an allowed autonomous-PR mode
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def guard(*, task_id: str, requested_mode: ExecutionMode | str, risk: str = "low",
          measurement_trusted: bool = True, has_verifier: bool = True,
          sandbox_available: bool = True, human_approved: bool = False,
          policy: GuardrailPolicy | None = None) -> GuardedDecision:
    """Cap a requested execution mode by the guardrail policy. Returns the allowed mode.

    Invariants: apply/merge modes require ``human_approved``; autonomous PR requires the
    policy to allow it AND low risk; any write-class mode requires sandbox + trusted
    measurement + a known verifier. Otherwise the mode is capped to the safe ceiling.
    """
    p = policy or GuardrailPolicy()
    req = ExecutionMode(requested_mode)
    reasons: list[str] = []
    allowed = req

    def _cap(to: ExecutionMode, why: str) -> None:
        nonlocal allowed
        if MODE_RANK[to] < MODE_RANK[allowed]:
            allowed = to
            reasons.append(why)

    # write-class modes need the full preconditions
    if MODE_RANK[req] >= _WRITE_FLOOR:
        if p.require_sandbox and not sandbox_available:
            _cap(ExecutionMode.DRAFT_PR, "no sandbox -> draft only")
        if p.require_trusted_measurement and not measurement_trusted:
            _cap(ExecutionMode.DRAFT_PR, "measurement untrusted -> draft only")
        if p.require_known_verifier and not has_verifier:
            _cap(ExecutionMode.DRAFT_PR, "no known verifier -> draft only")
    # apply/merge require human approval (unless an allowed autonomous mode)
    if req in (ExecutionMode.HUMAN_APPROVED_APPLY, ExecutionMode.HUMAN_APPROVED_MERGE) \
            and not human_approved:
        _cap(ExecutionMode.DRAFT_PR, "human approval required -> draft PR")
    # autonomous PR: off unless policy allows AND low risk
    if req == ExecutionMode.LOW_RISK_AUTONOMOUS_PR:
        if not p.allow_autonomous_pr:
            _cap(ExecutionMode.DRAFT_PR, "autonomous PR disabled by policy")
        elif risk != p.max_autonomous_risk:
            _cap(ExecutionMode.DRAFT_PR, f"risk={risk} > autonomous ceiling")

    autonomous_write = (allowed == ExecutionMode.LOW_RISK_AUTONOMOUS_PR
                        and p.allow_autonomous_pr)
    return GuardedDecision(
        task_id=task_id, requested_mode=req.value, allowed_mode=allowed.value,
        capped=allowed != req, autonomous_write=autonomous_write,
        reasons=reasons or ["requested mode permitted"])


@dataclass
class DraftPatch:
    task_id: str
    produced: bool
    patch_diff: str
    diff_lines: int
    verified_in_sandbox: bool
    applied: bool = False                      # HARD INVARIANT: always False here
    merged: bool = False                       # HARD INVARIANT: always False here

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["patch_diff"] = self.patch_diff[:4000]   # bound the stored diff
        return d


def produce_draft_patch(task, *, propose, verify_fn=None) -> DraftPatch:
    """Generate a draft patch in an ISOLATED repo and verify it — never touching the cwd.

    ``propose(task)`` returns proposed module content (e.g. from the live weak model).
    ``verify_fn(repo)`` runs the task's tests in the isolated repo. The real working tree is
    never modified: ``applied`` and ``merged`` stay False by construction.
    """
    from acp.agents.benchmark_suite import build_bench_repo, run_pytest

    content = propose(task)
    if content is None:
        return DraftPatch(task_id=task.name, produced=False, patch_diff="", diff_lines=0,
                          verified_in_sandbox=False)
    with tempfile.TemporaryDirectory() as d:
        repo = build_bench_repo(Path(d), task)         # isolated sandbox clone
        (repo / task.module_path).write_text(content)
        diff = subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True,
                              check=False).stdout
        passed = (verify_fn or run_pytest)(repo)
    return DraftPatch(
        task_id=task.name, produced=True, patch_diff=diff,
        diff_lines=sum(1 for ln in diff.splitlines()
                       if ln[:1] in "+-" and not ln.startswith(("+++", "---"))),
        verified_in_sandbox=bool(passed), applied=False, merged=False)
