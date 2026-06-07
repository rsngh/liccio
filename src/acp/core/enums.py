"""Domain enums (charter §7.1)."""

from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    TEST_GENERATION = "test_generation"
    DOCS = "docs"
    DEPENDENCY_UPDATE = "dependency_update"
    CI_FIX = "ci_fix"
    SECURITY_FIX = "security_fix"
    MIGRATION = "migration"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[self.value]

    def requires_human_review(self) -> bool:
        return self in (RiskLevel.HIGH, RiskLevel.CRITICAL)


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

    @property
    def terminal(self) -> bool:
        return self in (
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        )


class AttemptOutcome(str, Enum):
    """Fine-grained classification of a single agent attempt (Alpha 11/12 WS1).

    The core distinction is *conclusive task-quality* outcomes (which may update a
    model's solve-rate) vs *infra / inconclusive* outcomes (which update
    reliability/availability but must NOT poison capability measurement). This
    codifies the live-bakeoff lesson that infra timeouts and provider errors were
    being miscounted as model-quality failures.
    """

    TASK_SUCCESS = "task_success"
    TASK_FAILURE = "task_failure"
    VERIFICATION_FAILURE = "verification_failure"
    HARNESS_ACTIVATION_FAILURE = "harness_activation_failure"
    HARNESS_ADHERENCE_FAILURE = "harness_adherence_failure"
    # Solved the task, then a later call hung — the work is done; counts as success.
    INFRA_TIMEOUT_AFTER_SOLUTION = "infra_timeout_after_solution"
    # Timed out before any tool call — pure infra hang, no signal; inconclusive.
    INFRA_TIMEOUT_BEFORE_ACTION = "infra_timeout_before_action"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    PROVIDER_RETRY_EXCEEDED = "provider_retry_exceeded"
    INCONCLUSIVE = "inconclusive"

    @property
    def is_conclusive_quality(self) -> bool:
        """True if this outcome may update model solve-rate (a real task signal)."""
        return self in _CONCLUSIVE_QUALITY

    @property
    def is_success(self) -> bool:
        """True if the task was actually solved (verified), hang notwithstanding."""
        return self in (AttemptOutcome.TASK_SUCCESS,
                        AttemptOutcome.INFRA_TIMEOUT_AFTER_SOLUTION)

    @property
    def is_infra(self) -> bool:
        """True if this reflects infrastructure/provider behavior, not model skill."""
        return self in (
            AttemptOutcome.INFRA_TIMEOUT_BEFORE_ACTION,
            AttemptOutcome.INFRA_TIMEOUT_AFTER_SOLUTION,
            AttemptOutcome.PROVIDER_RATE_LIMIT,
            AttemptOutcome.PROVIDER_SERVER_ERROR,
            AttemptOutcome.PROVIDER_RETRY_EXCEEDED,
        )


_CONCLUSIVE_QUALITY = frozenset({
    AttemptOutcome.TASK_SUCCESS,
    AttemptOutcome.INFRA_TIMEOUT_AFTER_SOLUTION,  # solved -> conclusive success
    AttemptOutcome.TASK_FAILURE,
    AttemptOutcome.VERIFICATION_FAILURE,
    AttemptOutcome.HARNESS_ACTIVATION_FAILURE,
    AttemptOutcome.HARNESS_ADHERENCE_FAILURE,
})


class SkillStatus(str, Enum):
    """Lifecycle of a skill document (Alpha 15 WS2)."""

    DRAFT = "draft"          # authored, not yet validated
    CANDIDATE = "candidate"  # under optimization / held-out validation
    ACTIVE = "active"        # deployed (best validated version for its scope)
    ARCHIVED = "archived"    # superseded by a newer active version
    REJECTED = "rejected"    # failed validation / negative-transfer / contamination


class EvidenceKind(str, Enum):
    UNIT_TEST = "unit_test"
    INTEGRATION_TEST = "integration_test"
    TYPE_CHECK = "type_check"
    LINT = "lint"
    SECURITY_SCAN = "security_scan"
    UI_FLOW = "ui_flow"
    COVERAGE = "coverage"
    MUTATION_TEST = "mutation_test"
    STATIC_ANALYSIS = "static_analysis"
    LLM_JUDGE = "llm_judge"
    HUMAN_REVIEW = "human_review"
    POST_MERGE = "post_merge"


class EvidenceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIPPED = "skipped"
    ERROR = "error"


class AgentKind(str, Enum):
    FAKE = "fake"
    PATCH = "patch"
    CLAUDE = "claude"
    GEMINI = "gemini"
    CODEX = "codex"
    OPENHANDS = "openhands"
    SIMPLE_LLM = "simple_llm"


class WeakLabelValue(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SUSPICIOUS = "suspicious"
    NEEDS_REVIEW = "needs_review"
    UNKNOWN = "unknown"


class HumanVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"


class PolicyStatus(str, Enum):
    DRAFT = "draft"
    CHAMPION = "champion"
    CHALLENGER = "challenger"
    ARCHIVED = "archived"


class ExplorationMode(str, Enum):
    EXPLOIT = "exploit"
    EXPLORE = "explore"
    FORCED = "forced"
