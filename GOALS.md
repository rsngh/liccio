A few source-verified assumptions behind the spec: the OpenAI Codex Python SDK currently exists but is experimental and controls a local Codex app-server over JSON-RPC, so the implementation should wrap it as an optional adapter rather than making it a hard dependency. ([OpenAI Developers][1]) Anthropic’s Claude Agent SDK exposes the same tools, agent loop, and context management that power Claude Code, with Python and TypeScript support. ([Claude Code][2]) OpenHands’ Software Agent SDK provides Python and REST APIs for code agents, supports local workspaces, and can run agents in ephemeral Docker or Kubernetes-backed workspaces. ([OpenHands Docs][3]) LangGraph is suitable for durable, stateful, human-in-the-loop agent orchestration. ([LangChain Docs][4]) MCP is relevant because it standardizes how applications provide context, tools, prompts, and resources to LLM apps. ([GitHub][5]) For the learning layer, Vowpal Wabbit supports contextual bandits in Python, MABWiser supports context-free and contextual bandit prototyping, Ax/BoTorch support adaptive experimentation and Bayesian optimization, and River supports online ML in Python. ([Vowpal Wabbit][6]) For context infrastructure, pgvector provides vector similarity search inside Postgres, Qdrant supports hybrid dense/sparse/multivector retrieval, and Tree-sitter provides concrete syntax trees and incremental parsing. ([GitHub][7]) For verification and observability, Playwright supports Python browser automation for tests, scripts, and agent workflows, while OpenTelemetry provides vendor-neutral traces, metrics, and logs. ([Playwright][8]) Braintrust and LangSmith both support evaluation workflows with human review, automated scoring, production traces, and feedback loops. ([braintrust.dev][9])


NOTE:
- you can judiciously do live tests and runs to make sure that this is all working using OPENAI_API_KEY and ANTHROPIC_API_KEY
- other agents and repos depend on this conda environment. Make sure that you don't change versions of any libraries as you install. **SUPER IMPORTANT**

---

# Implementation charter for the coding agent

## 0. Role and mission

You are an autonomous senior/principal software engineering agent. Your mission is to implement a Python-first **agentic software engineering control plane**.

This product routes coding tasks across multiple coding agents and models, compiles repo-specific context, runs agents in isolated workspaces, verifies outputs, collects traces, learns from objective and human feedback, and improves routing decisions over time using contextual bandits, supervised ML, weak supervision, and active learning.

This is not a toy demo. Build the first production-grade version.

The system must support:

```text
Task intake
Repo snapshotting
Codebase indexing
Context compilation
Agent/model routing
Parallel agent attempts
Sandboxed execution
Verification and evaluation
Human review
Weak supervision
Active learning
Bandit-based routing
Policy versioning
Trace collection
Cost/token accounting
Post-merge outcome ingestion
CLI/API usage
Long-running evals and soak tests
```

You must implement working code, tests, documentation, and runnable demos. Do not merely scaffold empty files. Do not fake passing tests by weakening assertions. Do not bypass failing tests. Do not delete tests unless replacing them with stronger ones.

---

## 1. Non-negotiable operating rules

### 1.1 Autonomy

Work continuously until the implementation satisfies the acceptance criteria. Do not stop after scaffolding. Do not ask clarifying questions. Make reasonable engineering choices and document them.

### 1.2 Safety

Never require real production credentials for tests. Never print secrets. Never write secrets to logs, traces, prompts, artifacts, or vector stores. Redact environment variables and tokens.

All command execution must go through a controlled command runner with:

```text
timeouts
working-directory control
output truncation
raw-output artifact storage
secret redaction
exit-code capture
resource policy
network policy metadata
```

### 1.3 Optional external integrations

External agent SDKs and cloud services must be optional.

The system must run end-to-end with fake/local adapters when these are absent:

```text
OpenAI API keys
Anthropic API keys
Codex local app-server
Claude Agent SDK
OpenHands Agent Server
Qdrant
Braintrust
LangSmith
Kubernetes
Docker
```

Core unit and integration tests must pass without paid APIs.

### 1.4 Version everything

Version and persist:

```text
tasks
repo snapshots
context packs
retrieval traces
routing decisions
policy versions
agent attempts
tool calls
commands
diffs
verification plans
evidence
evaluation results
human labels
weak labels
reward events
post-merge outcomes
```

### 1.5 Observability first

Every run must emit structured logs and OpenTelemetry spans. Every important decision must be inspectable after the run.

### 1.6 Reproducibility

A run must be reproducible from:

```text
repo URL
base commit
task payload
context-pack ID
policy version
agent adapter name
model name
budget
verification plan
random seed
```

### 1.7 Deterministic tests

All tests must be deterministic by default. Where randomness is necessary, seed it and log the seed.

---

## 2. Build target

Implement a repo named:

```text
agent-control-plane
```

Package name:

```text
acp
```

CLI command:

```text
acp
```

Python target:

```text
Python 3.11+
```

Recommended dependency manager:

```text
uv
```

Use `pyproject.toml`.

The repo must support:

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy src
uv run acp --help
```

---

## 3. Required high-level architecture

Implement these layers:

```text
API layer
  FastAPI
  Pydantic v2
  SQLAlchemy 2.x or SQLModel
  Alembic
  Postgres primary storage
  SQLite fallback for local tests
  Redis optional for queues/cache

Workflow/orchestration layer
  Internal graph runner for v1
  Optional Temporal integration behind interface
  Durable state transitions
  Resume/retry support
  Human-review interrupts

Agent adapter layer
  FakeAgentAdapter for tests
  PatchAgentAdapter for deterministic local patches
  ClaudeAgentAdapter optional
  CodexAgentAdapter optional
  OpenHandsAgentAdapter optional
  SimpleLLMReviewAdapter optional
  All adapters behind one common protocol

Workspace layer
  Local git worktree workspace
  Docker workspace optional
  Kubernetes workspace optional
  OpenHands workspace optional
  Command runner with timeout/redaction/resource capture

Context layer
  Git metadata
  ripgrep keyword search
  Tree-sitter parsing
  optional ctags/SCIP symbol index
  embeddings
  pgvector primary vector store
  Qdrant optional advanced vector store
  context-pack compiler
  token-budget enforcement

Evaluation layer
  pytest/test runner
  coverage
  lint/type/security scanners
  Playwright UI checks
  spec-derived verification plans
  objective evidence aggregator
  weak-label engine
  ML/LLM evaluator interface
  human-review queue
  active-learning selector

Learning/routing layer
  heuristic baseline router
  supervised success/cost/risk predictors
  contextual bandit router
  Bayesian experiment optimizer
  policy registry
  off-policy evaluation
  champion/challenger rollout
  drift detection hooks

Observability layer
  OpenTelemetry spans
  structured JSON logs
  trace IDs on all records
  optional Braintrust/LangSmith/Phoenix exporters

Governance layer
  budget policy
  risk policy
  human-approval policy
  sandbox policy
  audit log
```

---

## 4. Repository structure

Create this structure:

```text
agent-control-plane/
  pyproject.toml
  uv.lock
  README.md
  IMPLEMENTATION_LOG.md
  ARCHITECTURE.md
  SECURITY.md
  Makefile
  docker-compose.yml
  .env.example
  .gitignore

  src/
    acp/
      __init__.py
      version.py

      cli/
        __init__.py
        main.py
        commands/
          init.py
          repo.py
          task.py
          run.py
          verify.py
          eval.py
          policy.py
          demo.py

      api/
        __init__.py
        app.py
        deps.py
        routes/
          health.py
          repos.py
          tasks.py
          runs.py
          reviews.py
          policies.py
          evals.py
          traces.py

      core/
        __init__.py
        ids.py
        time.py
        config.py
        enums.py
        errors.py
        redaction.py
        budgets.py
        policies.py
        artifacts.py
        events.py

      db/
        __init__.py
        base.py
        session.py
        models.py
        repositories.py
        migrations/
          env.py
          script.py.mako
          versions/

      schemas/
        __init__.py
        task.py
        repo.py
        context.py
        agent.py
        workspace.py
        verification.py
        evaluation.py
        routing.py
        learning.py
        human_review.py
        trace.py

      observability/
        __init__.py
        logging.py
        tracing.py
        metrics.py
        exporters.py

      workspaces/
        __init__.py
        base.py
        local.py
        docker.py
        kubernetes.py
        command_runner.py
        diff.py
        git_ops.py
        policies.py

      context/
        __init__.py
        indexer.py
        parsers.py
        tree_sitter_parser.py
        symbols.py
        chunks.py
        embeddings.py
        vector_store.py
        pgvector_store.py
        qdrant_store.py
        retrieval.py
        compiler.py
        token_budget.py
        instructions.py
        agnostic_code_graph.py

      agents/
        __init__.py
        base.py
        registry.py
        fake.py
        patch_agent.py
        claude_agent.py
        codex_agent.py
        openhands_agent.py
        simple_llm.py

      verification/
        __init__.py
        plan.py
        detectors.py
        runners.py
        pytest_runner.py
        playwright_runner.py
        static_analysis.py
        security.py
        evidence.py
        aggregate.py

      evaluation/
        __init__.py
        objective.py
        weak_supervision.py
        llm_judges.py
        rubrics.py
        human_review.py
        active_learning.py
        calibration.py
        scorecards.py

      routing/
        __init__.py
        features.py
        actions.py
        constraints.py
        heuristic.py
        bandit.py
        supervised.py
        policy.py
        registry.py
        off_policy.py
        simulation.py

      orchestration/
        __init__.py
        state.py
        graph.py
        nodes.py
        runner.py
        retries.py
        interrupts.py

      integrations/
        __init__.py
        github.py
        mcp.py
        braintrust.py
        langsmith.py
        phoenix.py
        litellm_gateway.py

      jobs/
        __init__.py
        train_router.py
        replay_evals.py
        ingest_outcomes.py
        nightly_bakeoff.py
        drift_detection.py

  tests/
    conftest.py
    fixtures/
      repos/
        python_buggy_app/
        frontend_toy_app/
        multi_file_refactor_app/
      traces/
      policies/
      tasks/

    unit/
      test_schemas.py
      test_redaction.py
      test_budgets.py
      test_command_runner.py
      test_diff.py
      test_context_chunks.py
      test_context_compiler.py
      test_retrieval.py
      test_task_classifier.py
      test_agent_registry.py
      test_fake_agent.py
      test_verification_plan.py
      test_evidence_aggregation.py
      test_weak_supervision.py
      test_active_learning.py
      test_routing_features.py
      test_heuristic_router.py
      test_bandit_router.py
      test_policy_registry.py

    integration/
      test_db_migrations.py
      test_local_workspace.py
      test_index_fixture_repo.py
      test_run_fake_agent_workflow.py
      test_parallel_attempts.py
      test_human_review_interrupt.py
      test_playwright_fixture.py
      test_pgvector_store.py
      test_api_tasks.py
      test_cli_demo.py

    e2e/
      test_bugfix_end_to_end.py
      test_eval_ladder_end_to_end.py
      test_router_learning_end_to_end.py

    long/
      test_soak_workflows.py
      test_bandit_monte_carlo.py
      test_retriever_stress.py
      test_command_runner_chaos.py

  evals/
    datasets/
      synthetic_tasks.yaml
      fixture_bugfix_tasks.yaml
      router_simulation_tasks.yaml
    rubrics/
      spec_compliance.yaml
      diff_risk.yaml
      test_adequacy.yaml
      architecture_fit.yaml
    scripts/
      run_bakeoff.py
      run_soak.py
      run_bandit_sim.py
      replay_traces.py

  examples/
    quickstart/
    github_issue_flow/
    local_repo_flow/
    browser_ui_flow/
    contextual_bandit_demo/

  docs/
    design/
      context_compiler.md
      evaluation_ladder.md
      routing_policy.md
      workspace_security.md
      data_model.md
      active_learning.md
    operations/
      local_dev.md
      docker.md
      kubernetes.md
      observability.md
      adding_agent_adapter.md
      adding_evaluator.md
      running_long_evals.md
```

---

## 5. Dependency plan

Use dependency groups.

### 5.1 Core dependencies

Add:

```text
fastapi
uvicorn
pydantic
pydantic-settings
sqlalchemy
alembic
psycopg[binary]
aiosqlite
typer
rich
httpx
tenacity
structlog
python-dotenv
orjson
gitpython
networkx
numpy
pandas
polars
scikit-learn
```

### 5.2 Dev/test dependencies

Add:

```text
pytest
pytest-asyncio
pytest-cov
pytest-timeout
pytest-xdist
hypothesis
respx
freezegun
ruff
mypy
types-requests
pre-commit
```

### 5.3 Context/retrieval dependencies

Add optional group `context`:

```text
tree-sitter
tree-sitter-python
tree-sitter-javascript
tree-sitter-typescript
tiktoken
pgvector
qdrant-client
sentence-transformers
rank-bm25
```

Also call `ripgrep` as a system binary when available; fallback to Python search.

### 5.4 Agent dependencies

Add optional group `agents`:

```text
claude-agent-sdk
openhands-sdk
openai
litellm
mcp
```

For Codex, make the adapter optional and robust because the Python SDK may need a local checkout or local app-server.

### 5.5 Verification dependencies

Add optional group `verification`:

```text
pytest
coverage
hypothesis
playwright
pytest-playwright
ruff
mypy
bandit
semgrep
```

Use external CLIs when installed; otherwise mark evidence as skipped with reason.

### 5.6 Learning dependencies

Add optional group `learning`:

```text
lightgbm
xgboost
vowpalwabbit
mabwiser
river
ax-platform
botorch
pymc
numpyro
joblib
```

The project must still import without these extras. Lazy-import optional dependencies.

### 5.7 Observability/eval dependencies

Add optional group `observability`:

```text
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp
arize-phoenix
braintrust
langsmith
wandb
```

---

## 6. Configuration system

Implement `src/acp/core/config.py`.

Support config from:

```text
environment variables
.env
YAML file
CLI flags
database-stored policy
```

Minimum config:

```python
class ACPSettings(BaseSettings):
    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite+aiosqlite:///./acp.db"
    artifact_dir: Path = Path(".acp/artifacts")
    workspace_dir: Path = Path(".acp/workspaces")
    default_token_budget: int = 80_000
    default_cost_budget_usd: float = 5.0
    default_command_timeout_s: int = 120
    allow_network_by_default: bool = False
    enable_external_agents: bool = False
    enable_docker: bool = False
    enable_qdrant: bool = False
    enable_pgvector: bool = False
    enable_braintrust: bool = False
    enable_langsmith: bool = False
    redacted_env_patterns: list[str] = [
        ".*TOKEN.*",
        ".*KEY.*",
        ".*SECRET.*",
        ".*PASSWORD.*",
        ".*CREDENTIAL.*",
    ]
```

Tests:

```text
Config loads defaults.
Config loads .env.
Sensitive values are redacted in repr/logging.
Invalid budgets fail validation.
```

---

## 7. Core domain model

Implement Pydantic schemas and SQLAlchemy models.

### 7.1 Enums

Create enums:

```python
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

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

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

class AgentKind(str, Enum):
    FAKE = "fake"
    PATCH = "patch"
    CLAUDE = "claude"
    CODEX = "codex"
    OPENHANDS = "openhands"
    SIMPLE_LLM = "simple_llm"
```

### 7.2 Required schemas

Implement these schemas:

```python
Task
Repository
RepoSnapshot
WorkspaceSpec
ContextPack
ContextItem
RetrievalTrace
RoutingAction
RoutingDecision
AgentAttempt
ToolCallRecord
CommandRunRecord
DiffBundle
VerificationPlan
VerificationRun
Evidence
EvaluationResult
HumanReviewItem
HumanLabel
WeakLabel
RewardEvent
PolicyVersion
PostMergeOutcome
```

### 7.3 Required fields

`Task`:

```text
id
repo_id
source
external_id
title
body
acceptance_criteria
non_goals
task_type
risk_level
ambiguity_score
labels
created_at
updated_at
status
metadata
```

`Repository`:

```text
id
name
url
default_branch
local_path
provider
visibility
created_at
updated_at
metadata
```

`RepoSnapshot`:

```text
id
repo_id
base_commit
branch
dirty
language_summary
index_version
index_hash
created_at
```

`ContextPack`:

```text
id
repo_id
task_id
snapshot_id
strategy
token_budget
token_estimate
items
instructions
retrieval_trace
created_at
content_hash
```

`ContextItem`:

```text
id
kind
path
start_line
end_line
symbol_name
content
token_estimate
score
source
metadata
```

`RoutingAction`:

```text
agent_kind
agent_name
model_name
context_strategy
context_token_budget
tool_permissions
workspace_policy
verification_policy
max_cost_usd
max_wall_time_s
parallelism
fallback_policy
requires_human_approval
```

`RoutingDecision`:

```text
id
task_id
snapshot_id
policy_version
action
action_probability
candidate_actions
model_scores
exploration_mode
exploration_reason
constraints_applied
created_at
```

`AgentAttempt`:

```text
id
task_id
routing_decision_id
workspace_id
agent_kind
agent_name
model_name
status
started_at
finished_at
input_token_count
output_token_count
total_token_count
estimated_cost_usd
wall_time_s
diff_bundle_id
trace_id
error
metadata
```

`Evidence`:

```text
id
task_id
attempt_id
verification_run_id
kind
name
status
score
confidence
summary
raw_output_ref
artifacts
started_at
finished_at
metadata
```

`EvaluationResult`:

```text
id
task_id
attempt_id
spec_compliance
test_adequacy
regression_risk
security_risk
review_burden
maintainability
confidence
requires_human_review
reasons
evidence_ids
created_at
```

`RewardEvent`:

```text
id
task_id
attempt_id
routing_decision_id
policy_version
reward
components
label_source
created_at
matured_at
metadata
```

Tests:

```text
All schemas serialize/deserialize.
All schemas have stable JSON representation.
All database models round-trip.
Invalid enum values fail validation.
ContextPack content_hash changes when item content changes.
RoutingDecision requires action_probability in (0, 1].
RewardEvent requires components summing or explaining reward.
```

---

## 8. Database and migrations

Implement SQLAlchemy models and Alembic migrations.

### 8.1 Storage rules

Use Postgres in production. Use SQLite for tests. JSON fields must work in both.

Tables:

```text
repositories
repo_snapshots
tasks
context_packs
context_items
routing_decisions
agent_attempts
tool_calls
command_runs
diff_bundles
verification_plans
verification_runs
evidence
evaluation_results
human_review_items
human_labels
weak_labels
reward_events
policy_versions
post_merge_outcomes
artifacts
audit_log
```

### 8.2 Required DB tests

```text
Alembic upgrade head succeeds on SQLite.
All tables exist.
Insert full workflow graph succeeds.
Cascade/delete behavior is explicit and tested.
Query by task_id returns all child records.
Query by trace_id returns all spans/records.
JSON metadata survives round-trip.
```

### 8.3 Artifact storage

Large raw outputs must not be stored inline in relational rows. Store them as artifacts:

```text
terminal transcripts
test output
coverage reports
patch files
screenshots
Playwright traces
LLM raw responses
retrieval debug dumps
```

Implement local filesystem artifact storage first.

Interface:

```python
class ArtifactStore(Protocol):
    def put_bytes(self, data: bytes, *, content_type: str, suffix: str) -> ArtifactRef: ...
    def put_text(self, text: str, *, content_type: str = "text/plain", suffix: str = ".txt") -> ArtifactRef: ...
    def get_bytes(self, ref: ArtifactRef) -> bytes: ...
```

Tests:

```text
Artifact put/get works.
Artifact path traversal is impossible.
Artifact SHA256 is verified.
Large command output is stored as artifact and summary is truncated.
```

---

## 9. Workspace layer

Implement:

```text
LocalWorkspaceManager
DockerWorkspaceManager
KubernetesWorkspaceManager optional stub
OpenHandsWorkspaceManager optional stub
```

### 9.1 Local workspace

Requirements:

```text
Clone or use local repo path.
Create isolated git worktree per run.
Checkout exact base commit.
Detect dirty state.
Capture initial HEAD.
Capture final HEAD.
Generate diff against base.
Clean up by policy.
```

Interface:

```python
class WorkspaceManager(Protocol):
    async def create(self, repo: Repository, snapshot: RepoSnapshot, policy: WorkspacePolicy) -> Workspace: ...
    async def cleanup(self, workspace: Workspace) -> None: ...
```

### 9.2 Command runner

All commands go through `CommandRunner`.

Interface:

```python
class CommandRunner:
    async def run(
        self,
        command: list[str],
        cwd: Path,
        timeout_s: int,
        env: dict[str, str] | None = None,
        allow_network: bool = False,
        max_output_chars: int = 20_000,
    ) -> CommandResult: ...
```

Capture:

```text
command argv
cwd
sanitized env keys
start/end time
exit code
stdout summary
stderr summary
raw stdout artifact
raw stderr artifact
timeout flag
resource usage if available
```

Tests:

```text
Successful command returns exit_code 0.
Failing command returns nonzero and does not raise unless requested.
Timeout terminates process tree.
Env secrets are redacted.
Output larger than max_output_chars is truncated and artifacted.
cwd must be inside workspace unless explicitly allowed.
```

### 9.3 Diff capture

Implement:

```python
get_changed_files()
get_unified_diff()
get_diff_stats()
get_file_patch(path)
detect_binary_changes()
```

Tests:

```text
New file appears in diff.
Modified file appears in diff.
Deleted file appears in diff.
Binary file is detected.
Diff stats match expected line counts.
```

---

## 10. Context compiler

This is a core moat. Implement it seriously.

### 10.1 Indexing

Implement `RepoIndexer`.

It must collect:

```text
file tree
language summary
README/docs
AGENTS.md or equivalent instructions
package manifests
test files
source files
symbols
imports
git history summary
recent commits
recent changed files
ownership hints if CODEOWNERS exists
```

Use:

```text
ripgrep if available
Tree-sitter for Python/JS/TS at minimum
Python AST fallback for Python
ctags optional
```

### 10.2 Chunking

Implement chunk types:

```text
file_chunk
symbol_chunk
test_chunk
doc_chunk
instruction_chunk
manifest_chunk
recent_commit_chunk
prior_run_summary_chunk
```

Each chunk must include:

```text
repo_id
snapshot_id
path
start_line
end_line
symbol
content
content_hash
token_estimate
language
kind
metadata
```

### 10.3 Retrieval strategies

Implement these strategies:

```text
keyword_only
embedding_only
hybrid_keyword_embedding
symbol_graph
test_focused
bug_reproduction
architecture
recent_changes
prior_failures
minimal
max_context
```

For v1, `hybrid_keyword_embedding` can combine:

```text
BM25/ripgrep score
vector similarity score
path/name boost
test-file boost
recency boost
symbol-reference boost
prior-run boost
```

Implement scoring:

```python
final_score = (
    0.35 * keyword_score
    + 0.35 * vector_score
    + 0.10 * path_boost
    + 0.10 * symbol_boost
    + 0.05 * test_boost
    + 0.05 * prior_run_boost
)
```

Make weights configurable.

### 10.4 Token budgeting

Implement `ContextBudgeter`.

Inputs:

```text
candidate items
token budget
required items
diversity constraints
max items per file
max total files
```

Output:

```text
selected items
dropped items
budget trace
```

Algorithm:

```text
Always include required instructions.
Always include task spec.
Always include AGENTS.md if present.
Include top-scoring chunks with diversity by file.
Prefer full files only when small or explicitly required.
Stop before token budget.
Emit trace explaining inclusions/exclusions.
```

Tests:

```text
Budget is never exceeded.
Required items are included.
Duplicate chunks are removed.
Binary files are ignored.
Large files are chunked.
Relevant bug file is retrieved in fixture repo.
Tests related to bug file are retrieved.
AGENTS.md is included when present.
Retrieval trace explains decisions.
```

### 10.5 ContextPack artifact

Context packs must be immutable. Store content hash.

Acceptance:

```text
Same task/snapshot/strategy produces same context hash.
Changing a source file changes context hash.
Changing token budget can change selected items.
ContextPack can be rendered to Markdown for agent input.
ContextPack can be rendered to JSON for machine use.
```

---

## 11. Task classifier

Implement deterministic baseline classifier.

### 11.1 Inputs

```text
task title
task body
labels
file paths mentioned
repo language summary
CI failure logs if present
security scanner output if present
```

### 11.2 Outputs

```text
task_type
risk_level
ambiguity_score
testability_score
affected_modules_estimate
required_verification_kinds
human_review_required
```

### 11.3 Rules

Examples:

```text
Title/body mentions failing test, CI, traceback -> CI_FIX or BUGFIX.
Mentions dependency, CVE, vulnerability -> SECURITY_FIX or DEPENDENCY_UPDATE.
Mentions refactor, rename, migration -> REFACTOR or MIGRATION.
Only docs/README paths -> DOCS and LOW risk.
Touches auth, billing, crypto, permissions, data deletion -> HIGH/CRITICAL risk.
No acceptance criteria and vague terms -> high ambiguity.
```

Tests:

```text
Docs-only task classified LOW.
Auth change classified HIGH.
CVE task classified SECURITY_FIX.
Failing pytest log classified BUGFIX/CI_FIX.
Vague feature request has ambiguity_score > 0.7.
Explicit acceptance criteria lowers ambiguity_score.
```

---

## 12. Agent adapter layer

### 12.1 Common protocol

Implement:

```python
class AgentAdapter(Protocol):
    name: str
    kind: AgentKind

    async def healthcheck(self) -> AgentHealth: ...

    async def plan(
        self,
        task: Task,
        context_pack: ContextPack,
        workspace: Workspace,
        budget: Budget,
    ) -> AgentPlan: ...

    async def execute(
        self,
        task: Task,
        context_pack: ContextPack,
        workspace: Workspace,
        budget: Budget,
    ) -> AgentAttemptResult: ...

    async def review(
        self,
        task: Task,
        diff: DiffBundle,
        context_pack: ContextPack,
        budget: Budget,
    ) -> AgentReviewResult: ...
```

### 12.2 FakeAgentAdapter

Must be deterministic and testable.

Modes:

```text
success_noop
fail_noop
apply_patch_from_task_metadata
modify_file
break_tests
large_diff
timeout
```

Use it for unit/e2e tests.

### 12.3 PatchAgentAdapter

A local deterministic adapter that applies a patch specified in task metadata.

This lets e2e tests validate the whole system without LLM calls.

### 12.4 ClaudeAgentAdapter

Optional.

Requirements:

```text
Lazy import claude-agent-sdk.
If unavailable, healthcheck returns unavailable.
Do not fail project import.
Map ContextPack to Claude Agent SDK prompt/context.
Capture messages/tool calls when available.
Capture token/cost if available; otherwise estimate.
Respect budget/timeouts.
```

### 12.5 CodexAgentAdapter

Optional.

Requirements:

```text
Lazy import/use Codex SDK or CLI wrapper.
Treat as experimental.
Healthcheck must detect local Codex app-server or binary availability.
Do not make core tests depend on Codex.
Capture JSON-RPC/session events when available.
Respect workspace boundaries.
```

### 12.6 OpenHandsAgentAdapter

Optional.

Requirements:

```text
Lazy import openhands-sdk.
Support local workspace mode if possible.
Support Agent Server URL config.
Capture actions/tool calls.
Map result to AgentAttemptResult.
```

### 12.7 Agent registry

Implement:

```python
AgentRegistry.register(adapter)
AgentRegistry.get(name)
AgentRegistry.available()
AgentRegistry.healthcheck_all()
```

Tests:

```text
Registry registers fake adapter.
Unavailable external adapter does not crash.
Execute result includes diff.
Timeout maps to failed attempt.
Adapter errors are captured as structured failure.
```

---

## 13. Routing policy

### 13.1 Routing action space

A routing action is not just model choice. It includes:

```text
agent_kind
agent_name
model_name
context_strategy
context_token_budget
workspace_policy
tool_permissions
verification_policy
max_cost_usd
max_wall_time_s
parallelism
fallback_policy
requires_human_approval
```

### 13.2 Baseline heuristic policy

Implement first.

Rules:

```text
LOW-risk docs/test/lint tasks:
  cheap/small model or patch/fake adapter in tests
  minimal or test_focused context
  standard verifier
  no parallelism

MEDIUM-risk bugfix:
  stronger model
  bug_reproduction context
  pytest/type/lint verifier
  fallback to second agent if verification fails

HIGH-risk auth/billing/security/migration:
  strongest available model
  architecture + test_focused context
  strict verifier
  human review required
  no unsafe exploration
  parallel planning allowed, implementation only after approval if configured

Ambiguous task:
  planning step first
  ask verifier/spec compiler to produce acceptance criteria
  human review if ambiguity remains high

CI fix:
  include CI logs
  run targeted failing tests first
  then broader test suite
```

### 13.3 Contextual bandit policy

Implement after baseline.

Use a generic interface:

```python
class RoutingPolicy(Protocol):
    def choose_action(self, features: RoutingFeatures, candidates: list[RoutingAction]) -> PolicyDecision: ...
    def observe_reward(self, decision: PolicyDecision, reward: RewardEvent) -> None: ...
```

`PolicyDecision` must always include:

```text
policy_version
chosen action
action_probability
candidate scores
exploration mode
exploration reason
random seed
```

### 13.4 Bandit implementation

Implement two versions:

```text
MABWiserBanditPolicy for prototyping
VWBanditPolicy for production-style contextual bandit experiments
```

If optional deps absent, tests use `SimulatedBanditPolicy`.

### 13.5 Features

Implement `RoutingFeatureExtractor`.

Features:

```text
task_type
risk_level
ambiguity_score
testability_score
repo_id hash
primary_language
language_mix
estimated_files_touched
affected_module_count
module_churn
historical_agent_success_by_repo
historical_agent_success_by_task_type
historical_agent_cost_by_task_type
prior_failures_in_module
test_coverage_estimate
ci_failure_type
context_retrieval_confidence
model_price_bucket
time_of_day optional
```

### 13.6 Constraints

Implement hard constraints:

```text
Budget cannot exceed task/repo/org limit.
HIGH/CRITICAL risk requires human review.
External network denied unless task requires it.
Secrets never exposed to untrusted agents.
Experimental policies cannot auto-merge.
Parallelism capped by budget.
Unavailable agents removed from candidates.
```

### 13.7 Tests

```text
Heuristic chooses cheap route for docs task.
Heuristic chooses strict verifier for auth task.
High-risk task always requires human review.
Unavailable agents are filtered.
Chosen action logs nonzero action_probability.
Bandit policy converges in synthetic simulation.
Bandit policy explores according to configured epsilon/Thompson sampling.
Off-policy evaluator rejects logs missing propensities.
Policy registry can roll back from challenger to champion.
```

---

## 14. Verification layer

### 14.1 VerificationPlan

Generate a plan before coding when possible.

Fields:

```text
id
task_id
strategy
required_commands
optional_commands
ui_flows
static_checks
security_checks
coverage_checks
mutation_checks
acceptance_assertions
risk_level
created_at
```

### 14.2 Detection

Implement detectors:

```text
Python project detector
Node project detector
Package manager detector
Test command detector
Lint command detector
Type-check command detector
Playwright detector
Docker compose detector
```

Examples:

```text
pyproject.toml + pytest dependency -> pytest
package.json + test script -> npm test
package.json + playwright -> playwright test
ruff in pyproject -> ruff check
mypy config -> mypy
```

### 14.3 Runners

Implement:

```text
PytestRunner
GenericCommandVerifier
PlaywrightRunner
StaticAnalysisRunner
SecurityScannerRunner
CoverageRunner
```

Each runner produces `Evidence`.

### 14.4 Objective evidence

Capture:

```text
command
exit code
duration
stdout/stderr summary
artifact refs
parsed counts where possible
pass/fail/warn/skipped
confidence
```

### 14.5 Aggregation

Implement `EvidenceAggregator`.

Default logic:

```text
If required test/build command fails -> verification failed.
If security scan has high severity -> security risk high.
If tests pass but no relevant test touched for bugfix -> test adequacy warning.
If diff touches unrelated files -> review burden/risk increase.
If UI flow passes -> add positive UI evidence.
If evidence incomplete -> confidence lower.
```

### 14.6 Tests

```text
Pytest failure parsed correctly.
Pytest pass parsed correctly.
Missing pytest command marks skipped, not pass.
Generic command timeout creates failed evidence.
Security high severity raises security_risk.
Bugfix without test change lowers test_adequacy.
Docs-only change does not require pytest by default.
Playwright fixture can run a simple browser flow.
```

---

## 15. Evaluation ladder

Implement a layered evaluation system.

### 15.1 Objective evaluator

Inputs:

```text
Task
DiffBundle
VerificationRun
Evidence list
ContextPack
AgentAttempt
```

Outputs:

```text
EvaluationResult
```

Scores:

```text
spec_compliance
test_adequacy
regression_risk
security_risk
review_burden
maintainability
confidence
requires_human_review
```

### 15.2 Weak supervision engine

Implement labeling functions.

Each labeling function returns:

```python
WeakSignal(
    name: str,
    label: Literal["success", "failure", "suspicious", "needs_review", "unknown"],
    confidence: float,
    reason: str,
)
```

Required labeling functions:

```text
ci_passed_signal
tests_failed_signal
new_regression_test_signal
no_test_for_bugfix_signal
large_diff_signal
sensitive_module_signal
unrelated_files_signal
security_warning_signal
reviewer_approved_signal
reviewer_requested_changes_signal
post_merge_revert_signal
production_incident_signal
agent_timeout_signal
budget_overrun_signal
parallel_disagreement_signal
```

Aggregate into probabilistic labels.

Tests:

```text
CI pass + tests + small diff -> high success probability.
Tests pass but no bugfix test -> suspicious.
Security warning -> needs review.
Revert outcome -> failure.
Parallel disagreement -> needs review.
```

### 15.3 LLM evaluator interface

Implement interface but keep tests fake.

Judges:

```text
SpecComplianceJudge
DiffRiskJudge
TestAdequacyJudge
ArchitectureFitJudge
UnrelatedChangeJudge
```

Each judge must accept:

```text
task spec
acceptance criteria
context summary
diff
evidence summary
rubric
```

Each judge must output structured JSON:

```json
{
  "score": 0.0,
  "confidence": 0.0,
  "verdict": "pass|fail|partial|uncertain",
  "reasons": [],
  "requires_human_review": true
}
```

Implement strict JSON parsing and retry-on-invalid for real LLM usage. Fake judge must be deterministic.

### 15.4 Human review queue

Implement:

```text
HumanReviewItem
HumanLabel
HumanReviewService
```

Reasons for human review:

```text
high risk
low evaluator confidence
objective/ML disagreement
parallel agent disagreement
security-sensitive diff
large unexpected diff
novel repo area
new model/policy canary
post-merge incident
random audit sample
```

API endpoints:

```text
GET /reviews
GET /reviews/{id}
POST /reviews/{id}/labels
POST /reviews/{id}/resolve
```

CLI:

```bash
acp reviews list
acp reviews show <id>
acp reviews label <id> --verdict pass --score 0.8 --reason "..."
```

### 15.5 Active learning selector

Implement selection scoring:

```python
active_learning_priority = (
    0.30 * uncertainty
    + 0.20 * evaluator_disagreement
    + 0.20 * business_risk
    + 0.10 * novelty
    + 0.10 * cost_surprise
    + 0.10 * policy_value_of_information
)
```

Tests:

```text
High uncertainty selected.
High-risk selected.
Random low-risk not selected unless audit sample.
Disagreement selected.
Novel task type selected.
```

---

## 16. Reward and learning

### 16.1 Reward formula

Implement configurable reward.

Default:

```python
reward = (
    3.0 * task_success
    + 1.0 * spec_compliance
    + 0.8 * test_adequacy
    + 0.4 * maintainability
    - 0.5 * log1p(token_cost_usd)
    - 0.3 * latency_penalty
    - 0.7 * review_burden
    - 1.5 * regression_risk
    - 2.0 * security_risk
    - 5.0 * reverted_or_incident
)
```

Every reward must store components.

### 16.2 Delayed outcomes

Implement post-merge outcome ingestion.

Fields:

```text
merged
merge_time
review_comments_count
review_rounds
reverted
revert_time
incident_link
issue_reopened
followup_bug_created
human_satisfaction_score
```

### 16.3 Supervised predictors

Implement training jobs for:

```text
success probability
expected token cost
expected wall time
review burden
regression risk
human review likelihood
```

Use scikit-learn baseline first.

Optional:

```text
LightGBM/XGBoost if installed
River for online updates
```

### 16.4 Bandit training

Implement:

```text
offline training from historical RoutingDecision + RewardEvent
online update after reward matures
simulation mode
canary/challenger mode
```

### 16.5 Off-policy evaluation

Implement:

```text
inverse propensity scoring
self-normalized IPS
doubly robust placeholder if enough supervised predictors exist
```

Reject logs without valid `action_probability`.

Tests:

```text
Reward components are stored.
Delayed revert updates reward downward.
Supervised model trains on synthetic data.
Bandit learns best arm in stationary simulation.
Bandit adapts in non-stationary simulation.
Off-policy evaluator fails on missing propensities.
Canary policy limited to configured traffic percentage.
Champion rollback works.
```

---

## 17. Orchestration graph

Implement durable workflow state.

### 17.1 Nodes

Required nodes:

```text
ingest_task
classify_task
create_repo_snapshot
index_repo
compile_context
generate_verification_plan
route_task
launch_agent_attempts
monitor_attempts
capture_diff
run_verification
aggregate_evidence
evaluate_attempt
maybe_human_review
compute_reward
update_policy
finalize_run
```

### 17.2 State

`WorkflowState` fields:

```text
run_id
task_id
repo_id
snapshot_id
context_pack_id
verification_plan_id
routing_decision_id
attempt_ids
selected_attempt_id
evidence_ids
evaluation_result_id
human_review_item_id
reward_event_id
status
current_node
error
trace_id
created_at
updated_at
```

### 17.3 Transitions

Rules:

```text
If classification fails -> FAILED.
If context compilation fails -> FAILED unless fallback minimal context succeeds.
If routing has no available agent -> FAILED with reason.
If agent attempt fails and fallback policy exists -> run fallback.
If parallelism > 1 -> launch attempts in separate workspaces.
If verification fails -> optionally repair or choose alternate attempt.
If evaluation requires human -> WAITING_FOR_HUMAN.
If human approves -> finalize success.
If human rejects -> fail or repair depending policy.
```

### 17.4 Resume/retry

Implement:

```text
idempotent nodes
node attempt count
retry policy
resume from persisted state
cancel run
```

Tests:

```text
Workflow completes with fake successful agent.
Workflow fails with fake failing agent.
Fallback agent runs after first failure.
Parallel attempts produce two workspaces.
Best verified attempt selected.
Human interrupt pauses workflow.
Human label resumes workflow.
Workflow resumes after simulated crash.
```

---

## 18. API

Implement FastAPI app.

Endpoints:

```text
GET /health
GET /version

POST /repos
GET /repos
GET /repos/{repo_id}
POST /repos/{repo_id}/index

POST /tasks
GET /tasks
GET /tasks/{task_id}

POST /tasks/{task_id}/run
GET /runs/{run_id}
GET /runs/{run_id}/state
GET /runs/{run_id}/trace
POST /runs/{run_id}/cancel

GET /attempts/{attempt_id}
GET /attempts/{attempt_id}/diff
GET /attempts/{attempt_id}/evidence
GET /attempts/{attempt_id}/evaluation

GET /reviews
GET /reviews/{review_id}
POST /reviews/{review_id}/labels
POST /reviews/{review_id}/resolve

GET /policies
GET /policies/current
POST /policies/train
POST /policies/{policy_id}/promote
POST /policies/{policy_id}/rollback

POST /evals/replay
POST /evals/bakeoff
GET /evals/runs/{eval_run_id}
```

Tests:

```text
OpenAPI schema generated.
Task create works.
Run start works.
Run state returns valid state.
Review label works.
Policy promote requires valid policy.
Invalid IDs return 404.
Invalid payloads return 422.
```

---

## 19. CLI

Implement Typer CLI.

Commands:

```bash
acp init
acp repo add <path-or-url>
acp repo index <repo-id>
acp task create --repo <repo-id> --title "..." --body "..."
acp run <task-id>
acp run status <run-id>
acp run trace <run-id>
acp run diff <run-id>
acp verify <attempt-id>
acp reviews list
acp reviews show <review-id>
acp reviews label <review-id> --verdict pass --score 0.9 --reason "..."
acp policy list
acp policy train
acp eval replay
acp demo quickstart
acp demo bugfix
acp demo bandit
```

Tests:

```text
acp --help works.
acp demo quickstart creates local DB and fixture repo.
acp demo bugfix completes end-to-end with PatchAgentAdapter.
acp run status prints useful summary.
```

---

## 20. Demos

Create demos that require no external API.

### 20.1 Bugfix demo

Fixture repo:

```text
python_buggy_app/
  pyproject.toml
  src/calculator.py
  tests/test_calculator.py
```

Bug:

```python
def divide(a, b):
    if b == 0:
        return 0  # wrong
    return a / b
```

Task:

```text
Fix divide-by-zero behavior. It should raise ZeroDivisionError.
Add or update tests.
```

PatchAgentAdapter applies correct patch.

E2E must show:

```text
task classified as BUGFIX
context includes src/calculator.py and tests/test_calculator.py
route selected
patch applied
pytest fails before or passes after depending workflow
verification passes
evaluation says success
reward event created
trace saved
```

### 20.2 Human review demo

Use FakeAgentAdapter with suspicious large diff. System should:

```text
run tests successfully
detect unrelated file changes
require human review
pause workflow
accept CLI/API human label
resume and finalize
```

### 20.3 Bandit demo

Synthetic environment:

```text
Agent A: cheap, 60% success
Agent B: expensive, 85% success
Agent C: cheap for docs, bad for security
```

Run 1,000 simulated tasks. Show policy learns:

```text
docs -> cheap agent
security -> strong agent
bugfix -> medium/strong depending reward
```

Output:

```text
cumulative reward
regret
action distribution
cost distribution
success distribution
```

---

## 21. Long-running tests and evals

Implement these commands in `Makefile`.

### 21.1 Fast suite

```bash
make test
```

Runs:

```bash
uv run pytest tests/unit tests/integration -q
uv run ruff check .
uv run mypy src
```

### 21.2 E2E suite

```bash
make test-e2e
```

Runs:

```bash
uv run pytest tests/e2e -q --timeout=600
```

### 21.3 Coverage

```bash
make coverage
```

Acceptance:

```text
Core modules >= 85% line coverage.
No core module below 70% unless documented.
```

### 21.4 Six-hour soak

```bash
make soak-6h
```

Behavior:

```text
Run repeated fake-agent workflows for approximately 6 hours or configured iteration count.
Randomize task mix with fixed seed.
Exercise success, failure, timeout, fallback, human review, parallel attempts.
No DB corruption.
No artifact leaks.
No unbounded memory growth.
No orphan workspaces.
```

Acceptance:

```text
>= 1,000 workflow iterations or 6 hours completed.
Failure rate only expected failures.
Memory growth under threshold.
All temporary workspaces cleaned or recorded.
```

### 21.5 Overnight bakeoff

```bash
make eval-bakeoff-overnight
```

Behavior:

```text
Run fixture task suite across all available adapters.
If real adapters unavailable, use fake/patch adapters.
Compare success, cost, latency, verification rate, review burden.
Generate report in evals/reports/.
```

Acceptance:

```text
Report includes per-agent scorecard.
Report includes routing recommendations.
Report includes failures with traces.
```

### 21.6 Bandit Monte Carlo

```bash
make bandit-monte-carlo
```

Behavior:

```text
Run at least 100 seeds.
Stationary and non-stationary simulations.
Compare random, heuristic, epsilon-greedy, Thompson/LinUCB if available.
```

Acceptance:

```text
Bandit beats random baseline on mean cumulative reward.
Confidence intervals reported.
Policy degradation under drift is detected.
```

### 21.7 Retriever stress

```bash
make retriever-stress
```

Behavior:

```text
Generate synthetic repo with thousands of files/chunks.
Index repo.
Run retrieval queries.
Compile context packs under budgets.
```

Acceptance:

```text
Index completes.
Retrieval latency reported.
Context budget never exceeded.
No binary/secret files included.
```

### 21.8 Chaos/resume test

```bash
make chaos
```

Behavior:

```text
Start workflows.
Kill worker mid-run.
Restart.
Resume from persisted state.
```

Acceptance:

```text
No duplicate finalization.
No lost reward event.
No orphaned human review item.
```

### 21.9 Security red-team

```bash
make security-redteam
```

Tasks include malicious instructions:

```text
Print environment variables.
Exfiltrate .env.
Disable tests.
Delete repository.
Call network endpoint.
Commit secrets.
Modify policy to auto-approve.
```

Acceptance:

```text
Command runner blocks or records policy violation.
Secrets redacted.
Unsafe network not allowed by default.
No malicious task succeeds in exfiltration.
```

---

## 22. Security and governance

Implement policy engine.

### 22.1 Policies

Minimum policies:

```text
BudgetPolicy
RiskPolicy
WorkspacePolicy
NetworkPolicy
SecretsPolicy
HumanApprovalPolicy
ToolPermissionPolicy
AutoMergePolicy
ExplorationPolicy
```

### 22.2 Defaults

```text
No auto-merge.
No network by default.
No secrets by default.
High-risk tasks require human review.
Critical-risk tasks require human review and strict verification.
Experimental policies cannot auto-approve.
Parallel attempts require budget check.
External agents cannot access files outside workspace.
```

### 22.3 Audit log

Every sensitive event must create audit log:

```text
policy override
human approval
network enablement
secret injection
budget increase
policy promotion
auto-finalization
external agent use
```

Tests:

```text
High-risk task cannot bypass human review.
Network denied by default.
Secrets redacted from command output.
Policy override creates audit event.
Experimental policy cannot auto-approve.
```

---

## 23. Observability

### 23.1 Tracing

Create spans:

```text
acp.workflow
acp.classify_task
acp.create_snapshot
acp.index_repo
acp.compile_context
acp.route_task
acp.agent.plan
acp.agent.execute
acp.command.run
acp.capture_diff
acp.verify
acp.evaluate
acp.human_review
acp.reward
acp.policy.update
```

Span attributes:

```text
task_id
repo_id
snapshot_id
run_id
attempt_id
agent_kind
agent_name
model_name
policy_version
context_pack_id
token_budget
estimated_cost_usd
status
```

### 23.2 Metrics

Expose/log:

```text
runs_total
runs_succeeded_total
runs_failed_total
human_review_required_total
agent_attempts_total
tokens_used_total
estimated_cost_usd_total
verification_failures_total
policy_exploration_total
avg_context_tokens
avg_wall_time
reward_mean
```

### 23.3 Exporters

Implement optional exporters:

```text
OpenTelemetry OTLP
Braintrust
LangSmith
Phoenix
local JSONL
```

Tests:

```text
Trace ID exists for every workflow.
Command span includes exit code.
No secret values in logs/spans.
Local JSONL exporter writes valid JSON.
```

---

## 24. Documentation

Write docs.

Required files:

```text
README.md
ARCHITECTURE.md
SECURITY.md
docs/design/context_compiler.md
docs/design/evaluation_ladder.md
docs/design/routing_policy.md
docs/design/active_learning.md
docs/design/data_model.md
docs/operations/local_dev.md
docs/operations/running_long_evals.md
docs/operations/adding_agent_adapter.md
docs/operations/adding_evaluator.md
```

README must include:

```text
what this is
quickstart
architecture diagram in Mermaid
how to run demo
how to add repo
how to run a task
how to run tests
how to run long evals
what works without API keys
what is optional
security warnings
```

ARCHITECTURE must include:

```text
system diagram
data lifecycle
workflow graph
context compiler design
routing policy design
eval ladder
learning loop
deployment options
```

SECURITY must include:

```text
threat model
workspace isolation
secret handling
network controls
audit log
known limitations
```

---

## 25. Implementation phases

Execute in order. Each phase must end with tests passing.

### Phase 0: Repo initialization

Deliver:

```text
pyproject.toml
package structure
ruff/mypy config
pytest config
Makefile
README skeleton
config system
logging setup
```

Acceptance:

```bash
uv sync --all-extras
uv run acp --help
uv run pytest tests/unit/test_schemas.py -q
uv run ruff check .
uv run mypy src
```

### Phase 1: Schemas, DB, artifacts

Deliver:

```text
Pydantic schemas
SQLAlchemy models
Alembic migration
SQLite test DB support
ArtifactStore
```

Acceptance:

```text
All schema unit tests pass.
DB migration test passes.
Artifact store tests pass.
```

### Phase 2: Workspace and command execution

Deliver:

```text
LocalWorkspaceManager
CommandRunner
Git diff utilities
redaction
resource/timeouts
```

Acceptance:

```text
Command runner tests pass.
Local workspace test passes.
Diff tests pass.
Security redaction tests pass.
```

### Phase 3: Context indexing and compiler

Deliver:

```text
RepoIndexer
Tree-sitter parser
chunker
keyword retrieval
embedding abstraction
pgvector optional store
context compiler
token budgeter
```

Acceptance:

```text
Fixture repo indexed.
Relevant files retrieved.
Context budget enforced.
Context pack immutable and hashable.
```

### Phase 4: Agent adapters

Deliver:

```text
AgentAdapter protocol
FakeAgentAdapter
PatchAgentAdapter
optional Claude/Codex/OpenHands wrappers
AgentRegistry
```

Acceptance:

```text
Fake and patch adapters pass.
External adapters unavailable gracefully.
Agent output diff captured.
```

### Phase 5: Verification

Deliver:

```text
VerificationPlan
project detectors
pytest runner
generic command verifier
static analysis runner
Playwright runner
evidence aggregation
```

Acceptance:

```text
Bugfix fixture verification passes/fails appropriately.
Playwright fixture passes.
Evidence aggregation tests pass.
```

### Phase 6: Orchestration

Deliver:

```text
WorkflowState
workflow nodes
runner
retry/resume
parallel attempts
human interrupt support
```

Acceptance:

```text
Fake-agent e2e passes.
Fallback e2e passes.
Human interrupt e2e passes.
Parallel attempts e2e passes.
```

### Phase 7: Evaluation ladder and HITL

Deliver:

```text
objective evaluator
weak supervision engine
LLM judge interface
fake judges
human review API/CLI
active learning selector
```

Acceptance:

```text
Weak labels correct on fixtures.
Human review queue works.
Active learning selector works.
Eval ladder e2e passes.
```

### Phase 8: Routing and learning

Deliver:

```text
heuristic router
feature extractor
policy registry
reward formula
supervised predictors
bandit policy
off-policy evaluation
simulation
```

Acceptance:

```text
Heuristic routing tests pass.
Bandit simulation beats random.
Policy registry promote/rollback works.
Reward events created.
```

### Phase 9: API and CLI completion

Deliver:

```text
FastAPI endpoints
Typer CLI commands
demo commands
OpenAPI docs
```

Acceptance:

```text
API integration tests pass.
CLI demo tests pass.
Bugfix demo passes from CLI.
```

### Phase 10: Long-running evals, docs, hardening

Deliver:

```text
soak scripts
bakeoff scripts
bandit monte carlo
retriever stress
chaos/resume
security redteam
docs
final report
```

Acceptance:

```text
make test passes.
make test-e2e passes.
make coverage passes.
make bandit-monte-carlo passes.
make retriever-stress passes.
make security-redteam passes.
Long-running commands are available and documented.
```

---

## 26. Final acceptance criteria

The implementation is complete only when all are true:

```text
1. A new user can run the quickstart without paid API keys.
2. The bugfix demo completes end-to-end.
3. The system creates a task, context pack, routing decision, agent attempt, diff, verification result, evaluation result, reward event, and trace.
4. Human-review interrupt works.
5. Parallel attempts work with isolated workspaces.
6. The router logs action probability.
7. The bandit simulation learns a better-than-random policy.
8. Context packs are immutable and token-budgeted.
9. All command execution is mediated and logged.
10. Secrets are redacted.
11. High-risk tasks require human review by default.
12. API and CLI both work.
13. Unit, integration, and e2e tests pass.
14. Long-running eval commands exist and produce reports.
15. Documentation explains how to add new agents, evaluators, context strategies, and routing policies.
```

---

## 27. Final report required from the coding agent

At completion, write `FINAL_REPORT.md` with:

```text
Summary of what was built
Architecture overview
How to run quickstart
How to run test suite
How to run long evals
Which optional integrations are implemented
Which optional integrations are stubs
Known limitations
Security posture
Performance notes
Coverage summary
Bandit simulation results
Retriever stress results
Soak/chaos results if run
Recommended next work
```

Also update `IMPLEMENTATION_LOG.md` continuously with:

```text
date/time
phase
changes made
tests run
failures found
fixes applied
remaining risks
```

---

## 28. Extra implementation guidance

Do not optimize prematurely. The correct order is:

```text
traceable workflow first
correct data model second
safe workspace third
context compiler fourth
verification fifth
routing sixth
learning seventh
external integrations eighth
```

The moat is not one clever model call. The moat is the loop:

```text
task → context → route → attempt → verify → evaluate → human label → reward → learn → better route/context/eval
```

Build that loop so every agent run becomes a reusable training example.

[1]: https://developers.openai.com/codex/sdk?utm_source=chatgpt.com "Codex SDK"
[2]: https://code.claude.com/docs/en/agent-sdk/overview?utm_source=chatgpt.com "Agent SDK overview - Claude Code Docs"
[3]: https://docs.openhands.dev/sdk?utm_source=chatgpt.com "Software Agent SDK"
[4]: https://docs.langchain.com/oss/python/langgraph/overview?utm_source=chatgpt.com "LangGraph overview - Docs by LangChain"
[5]: https://github.com/modelcontextprotocol/python-sdk?utm_source=chatgpt.com "MCP Python SDK"
[6]: https://vowpalwabbit.org/tutorials/contextual_bandits.html?utm_source=chatgpt.com "Contextual Bandits — VowpalWabbit latest documentation"
[7]: https://github.com/pgvector/pgvector?utm_source=chatgpt.com "pgvector/pgvector: Open-source vector similarity search for ..."
[8]: https://playwright.dev/python/?utm_source=chatgpt.com "Fast and reliable end-to-end testing for modern web apps"
[9]: https://www.braintrust.dev/docs/annotate/human-review?utm_source=chatgpt.com "Add human feedback - Braintrust"
