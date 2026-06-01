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
