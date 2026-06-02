"""Deterministic viability assessor (Alpha 7, WS1).

Maps a `TaskClassification` + task signals to a `ViabilityAssessment`: which agent
classes / context strategies are viable, whether a cheap model suffices or a true
harness is required, whether human review is mandatory, and whether to abstain.

Fully deterministic and rule-based (no ML), mirroring `core/classifier.py`. The
rules encode the product's risk posture:

* docs / trivial low-risk work -> a cheap simple model adapter is viable
* security / high-risk work -> a true harness + strict verification + human review
* highly ambiguous work -> plan / human review first
* no tests AND no spec -> abstain (or spec-generation first), because there is no
  way to verify success
"""

from __future__ import annotations

from acp.core.enums import RiskLevel, TaskType
from acp.schemas.task import Task, TaskClassification
from acp.schemas.viability import (
    CapabilityRequirement,
    ModelStrengthRequirement,
    ViabilityAssessment,
)

# Task types where a single-shot simple model adapter is a reasonable first try.
_CHEAP_OK = {TaskType.DOCS, TaskType.DEPENDENCY_UPDATE}
# Task types that demand a real tool-loop harness (multi-file, run tests, iterate).
_HARNESS_TYPES = {TaskType.SECURITY_FIX, TaskType.MIGRATION, TaskType.FEATURE}
_AMBIGUITY_ABSTAIN = 0.85
_AMBIGUITY_REVIEW = 0.6
_TESTABILITY_FLOOR = 0.2


def assess_viability(task: Task, cls: TaskClassification) -> ViabilityAssessment:
    reasons: list[str] = []
    features: dict[str, float] = {
        "ambiguity": cls.ambiguity_score,
        "testability": cls.testability_score,
        "risk_rank": float(cls.risk_level.rank if isinstance(cls.risk_level, RiskLevel)
                           else RiskLevel(cls.risk_level).rank),
    }
    risk = cls.risk_level if isinstance(cls.risk_level, RiskLevel) else RiskLevel(cls.risk_level)
    ttype = cls.task_type if isinstance(cls.task_type, TaskType) else TaskType(cls.task_type)

    # --- model strength -------------------------------------------------
    cheap_ok = ttype in _CHEAP_OK and risk.rank <= RiskLevel.MEDIUM.rank
    harness_required = ttype in _HARNESS_TYPES or risk.requires_human_review()
    if harness_required:
        reasons.append(f"{ttype.value}/{risk.value} requires a true tool-loop harness")
        cheap_ok = False
    tier = "frontier" if harness_required else ("standard" if not cheap_ok else "basic")
    model_strength = ModelStrengthRequirement(
        cheap_model_viable=cheap_ok, true_harness_required=harness_required,
        min_capability_tier=tier,
        reason=("cheap single-shot viable" if cheap_ok
                else "needs iterative tool use / verification"),
    )

    # --- viable agent classes ------------------------------------------
    if cheap_ok:
        agent_classes = ["simple_model", "acp_harness"]
    elif harness_required:
        agent_classes = ["acp_harness", "vendor"]
    else:
        agent_classes = ["acp_harness", "simple_model"]

    # --- context strategies --------------------------------------------
    if ttype == TaskType.BUGFIX:
        strategies = ["bug_reproduction", "test_focused", "hybrid_keyword_embedding"]
    elif ttype == TaskType.TEST_GENERATION:
        strategies = ["test_focused", "hybrid_keyword_embedding"]
    elif ttype in (TaskType.REFACTOR, TaskType.MIGRATION):
        strategies = ["architecture", "recent_changes", "hybrid_keyword_embedding"]
    elif ttype == TaskType.DOCS:
        strategies = ["minimal", "hybrid_keyword_embedding"]
    else:
        strategies = ["hybrid_keyword_embedding", "minimal"]

    # --- capability requirements ---------------------------------------
    caps = [CapabilityRequirement(name="write_files", required=True)]
    if cls.required_verification_kinds:
        caps.append(CapabilityRequirement(name="run_tests", required=True,
                                          reason="verification plan needs test execution"))
    if (cls.affected_modules_estimate or 1) > 1:
        caps.append(CapabilityRequirement(name="multi_file_edit", required=True))

    # --- human review ---------------------------------------------------
    human = bool(cls.human_review_required) or risk.requires_human_review() \
        or cls.ambiguity_score >= _AMBIGUITY_REVIEW
    if cls.ambiguity_score >= _AMBIGUITY_REVIEW:
        reasons.append("ambiguous task — human review recommended")

    # --- abstention -----------------------------------------------------
    abstain = False
    abstention: list[str] = []
    no_tests = cls.testability_score < _TESTABILITY_FLOOR
    no_spec = not (task.acceptance_criteria or (task.body and len(task.body) > 20))
    if cls.ambiguity_score >= _AMBIGUITY_ABSTAIN:
        abstain = True
        abstention.append("ambiguity too high to attempt safely — needs clarification")
    if no_spec:
        # No acceptance criteria and no meaningful description: success is
        # unverifiable, so abstain and require spec inference first. A low
        # testability score reinforces this.
        abstain = True
        detail = "no spec (no acceptance criteria / empty body)"
        if no_tests:
            detail = "no tests and no spec"
        abstention.append(f"{detail} — success is unverifiable; "
                          "generate a spec/tests first")
        caps.append(CapabilityRequirement(name="spec_inference", required=True,
                                          reason="no acceptance criteria provided"))

    parallelism = 2 if (harness_required and risk.rank >= RiskLevel.HIGH.rank) else 1

    confidence = round(
        0.5 + 0.25 * (1 - cls.ambiguity_score) + 0.25 * cls.testability_score, 3
    )

    return ViabilityAssessment(
        task_id=task.id, repo_id=task.repo_id, task_type=ttype, risk_level=risk,
        ambiguity_score=cls.ambiguity_score, testability_score=cls.testability_score,
        available_evidence=list(cls.required_verification_kinds),
        viable_agent_classes=agent_classes,
        viable_context_strategies=strategies,
        required_verification=list(cls.required_verification_kinds),
        capability_requirements=caps,
        model_strength=model_strength,
        cheap_model_viable=cheap_ok,
        true_harness_required=harness_required,
        human_review_required=human,
        parallelism_recommended=parallelism,
        abstain=abstain,
        abstention_reasons=abstention,
        confidence=confidence,
        supporting_features=features,
    )
