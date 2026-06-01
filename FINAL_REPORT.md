# Final Report — agent-control-plane (`acp`)

> **`CURRENT_STATUS.md` is the source of truth** for status, test counts, and
> coverage. The round-by-round build narrative is archived in `HISTORY.md`, and
> the latest gate is `ALPHA4_CHECKLIST.md`. This file is a historical narrative;
> numbers here may lag. Per-subsystem reality is tabulated below.

## Subsystem reality (real / service-backed / simple adapter / true harness / fallback / stub)

| Subsystem | Status |
|---|---|
| Workflow loop + durable resume | **real local** (exhaustive crash-resume tested) |
| Persistence / provenance / RunGraph | **real local** (full graph reconstructs after restart) |
| Command execution (local) | **real local**, cwd-contained + secret-scrubbed (not OS sandbox) |
| Command execution (Docker) | **real** `DockerCommandRunner` (in-container); skipped w/o daemon |
| Context compiler + retrieval | **real local** (hybrid; adversarial benchmark) |
| Vector store — InMemory | **real local** |
| Vector store — Qdrant | **real service-backed** (qdrant-client engine; live test) |
| Vector store — pgvector | **explicit fallback** until a DSN is configured (visible `backend` flag) |
| Embeddings — hashing | **real local**; OpenAI/sentence-transformers **optional real** |
| Agent: fake / patch | **real** deterministic baselines |
| Agent: Claude/Codex/OpenHands/SimpleLLM | **simple model adapters** (`is_harness=False`) |
| Agent: OpenAIHarnessAdapter | **true harness** (`is_harness=True`) — tool-loop + trace capture |
| Eval ladder + reports | **real**, persisted as `EvalRun`/`EvalReport` entities |
| Routing policy | **real** persisted bandit (survives restart) + OPE + drift |
| LLM judges | **fake deterministic** by default; calibration harness vs human/post-merge |
| Observability | **real** in-process spans + JSONL; OTel exporter optional |

## Summary of what was built

A local v0/alpha (not yet production-grade — see `CURRENT_STATUS.md`), Python-first
agentic software-engineering **control plane** implementing the full loop:

```
task → context → route → attempt → verify → evaluate → human label → reward → learn
```

All 11 phases of the charter (§25) were delivered, each ending green. The system
runs end-to-end with **no paid API keys** using fake/patch adapters; real Claude/
OpenAI/Codex/OpenHands adapters are optional and lazy-imported.

## Architecture overview

See `ARCHITECTURE.md`. 12 layers behind protocols: API (FastAPI) / CLI (Typer) /
core (config, redaction, artifacts, classifier, governance) / db (SQLAlchemy +
Alembic + EntityStore) / schemas (Pydantic v2) / workspaces (git worktrees +
mediated CommandRunner) / context (index→retrieve→budget→pack) / agents /
verification / evaluation ladder / routing & learning / orchestration (durable
15-node runner) / observability (tracing, metrics, JSONL export).

## How to run quickstart

```bash
uv sync --all-extras
uv run acp --help
uv run acp demo bugfix       # full loop, no keys -> status: succeeded
uv run acp demo bandit       # bandit beats random
```

## How to run the test suite

```bash
uv run pytest -q                 # 151 tests (unit + integration + e2e + long)
uv run ruff check . && uv run mypy src
make coverage
```

## How to run long evals

```bash
make bandit-monte-carlo          # vs random, N seeds + drift, 95% CI
make retriever-stress
make chaos
make security-redteam
make soak-6h
make eval-bakeoff-overnight
```

## Implemented optional integrations

- OpenAI adapter (`SimpleLLMReviewAdapter`) — **live-tested** against the bugfix
  fixture (token capture, real edit).
- tree-sitter (python) + tiktoken + rank-bm25 + scikit-learn (installed extras).
- OpenTelemetry-ready tracing surface; local JSONL exporter implemented.

## Stubs / behind-protocol (optional, degrade gracefully)

- Claude (anthropic SDK not installed here), Codex (local binary), OpenHands SDK.
- Docker / Kubernetes workspace backends.
- pgvector / Qdrant vector stores, sentence-transformers, MABWiser / VW bandits,
  Braintrust / LangSmith / Phoenix exporters, Playwright, bandit/semgrep CLIs.
  All report "unavailable" or fall back deterministically; project imports without
  them.

## Known limitations

- Local `CommandRunner` enforces cwd containment + redaction + timeouts but not
  OS-level syscall/network sandboxing (use Docker/K8s backend for hard isolation).
- Cross-process resume from persisted `WorkflowState` is a follow-up (entities are
  persisted; the run registry is in-process).
- Heavy optional deps are declared as lazy-import targets rather than pinned into
  extras, to keep `uv sync --all-extras` fast/reliable.

## Security posture

Secrets never logged/traced/stored (`SecretStr` + `Redactor` in logging, span
export, and command output). All exec mediated. Network denied by default,
no auto-merge, high/critical risk requires human review, experimental policies
cannot auto-approve, every override is audited. Red-team suite passes.

## Performance notes

Full unit+integration+e2e+long suite runs in ~40s. Context compile over a 400-file
synthetic repo with a 5k-token budget completes well under a second and never
exceeds the budget.

## Coverage summary

~83% line coverage across `src/acp` (TOTAL 3737 stmts). Below the 85% target
mainly due to optional adapter/stub code paths (Docker/K8s/Codex/OpenHands real
execution, optional exporters). Core loop modules (schemas, db, workspaces,
context, verification, orchestration, routing) are well above 85%.

## Bandit simulation results

`run_bandit_sim.py --seeds 20 --rounds 500`: bandit beats random in **20/20**
seeds; mean reward margin **167.8 ± 25.9 (95% CI)**; positive under drift
(margin ~183.8). Converges to the strong arm on the security context.

## Retriever stress results

400-file synthetic repo indexed + compiled with a 5,000-token budget: budget
never exceeded for retrieved items, secrets/binaries excluded, deterministic
`content_hash` across repeated compiles.

## Soak / chaos results

Soak (sampled, fixed seed): mixed success/fail/human-review statuses, no orphan
workspaces. Chaos/resume: no duplicate finalization, reward event present exactly
once, resume idempotent.

## Acceptance criteria (charter §26)

1. quickstart without paid keys ✓  2. bugfix demo e2e ✓  3. full provenance chain
(task/context/route/attempt/diff/verify/eval/reward/trace) ✓  4. human-review
interrupt ✓  5. parallel isolated workspaces ✓  6. router logs action_probability
✓  7. bandit beats random ✓  8. immutable token-budgeted context packs ✓
9. all exec mediated+logged ✓  10. secrets redacted ✓  11. high-risk requires
human review ✓  12. API + CLI work ✓  13. unit/integration/e2e pass (151) ✓
14. long-eval commands + reports ✓  15. docs for adding agents/evaluators/
strategies/policies ✓

## Recommended next work

- Cross-process durable resume (persist + reload WorkflowState).
- Wire real Claude / Codex / OpenHands adapters and Docker workspace in CI behind
  opt-in markers.
- pgvector/Qdrant retrieval backends + sentence-transformers embeddings.
- Doubly-robust OPE once supervised predictors have production data.
- Push core coverage of optional paths above 85% with backend integration tests.
