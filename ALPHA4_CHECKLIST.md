# Alpha 4 — multi-harness empirical router: PR / merge checklist

Alpha 4 makes the product's central promise real:

> Same task, same repo, same context, **multiple real harnesses**, normalized
> traces, objective verification, calibrated evaluation, and learned routing.

## What changed since Alpha 3

| Block | Delivered |
| --- | --- |
| E | **Second true harness** — `ClaudeHarnessAdapter` (Anthropic tool-use loop), sharing the LLM-agnostic `harness_base` core with `OpenAIHarnessAdapter`. Two true harness classes now exist. |
| B | Execution-backend **governance enforced in orchestration**: true harness on local backend is blocked (audited) unless `allow_local_harness`; docker allowed; simple-model-on-local audited; fake/patch allowed. |
| C | **AgentTrace is a mandatory invariant** — every attempt carries exactly one normalized trace (synthesized if the adapter exposes none); present in the run graph after restart. |
| D | **Live Docker evidence pack** — `run_docker_security_check.py` proves non-root / no-network / mem+pid caps / workspace containment / cleanup; explicit skip when Docker is absent. |
| F | **Multi-harness no-patch bakeoff** — matrix of no-patch task classes × adapters; per-cell metrics + failure taxonomy; persisted as an `EvalRun`. Upgrades the bakeoff from "can solve" to "can compare". |
| G | **Router learns from the bakeoff** — bakeoff outcomes (quality minus cost penalty) replay into the bandit; idempotent per `EvalRun`; after replay the router prefers the better agent. |
| H | **Calibrated evaluator loop** — per-signal Brier/accuracy/correlation vs human + post-merge truth; human-review **threshold recommendation**; persisted as `EvalRun(kind=calibration)`. |
| A | Docs reconciled (`CURRENT_STATUS` / `FINAL_REPORT` / this checklist); historical report sections archived to `HISTORY.md`; doc-consistency test added. |

## Required artifacts (committed under `reports/` and `evals/reports/`)

- [x] `reports/pytest.txt`
- [x] `reports/coverage.txt`
- [x] `evals/reports/docker_security.json` (explicit skip when Docker absent)
- [x] `evals/reports/no_patch_bakeoff.json`
- [x] `evals/reports/multi_harness_trace_bakeoff.json`
- [x] `evals/reports/calibration.json`

## Gate commands

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
make security-redteam
make bandit-monte-carlo
make retriever-stress
make alpha4-artifacts        # docker-security + multi-harness-bakeoff + calibration
```

## Optional live gates (real keys; skipped by default)

```bash
make live-openai             # pytest -m live_openai
make live-second-harness     # pytest -m live_second_harness  (Anthropic)
make live-docker             # pytest -m live_docker
```

Verified live during development: the OpenAI harness and the Claude harness each
solved a no-patch bugfix end to end, and a live multi-harness bakeoff compared
both real harnesses on the same task (both made tool calls; both solved).

## Acceptance

- Two true harness classes exist and are registered (`openai_harness`,
  `claude_harness`).
- A true harness cannot run on the local backend without an audited override.
- Every attempt has a normalized `AgentTrace`, durable across restart.
- The multi-harness bakeoff persists comparable per-adapter metrics.
- Replaying a bakeoff `EvalRun` changes the router's preferred action.
- Calibration emits per-signal scores + a human-review threshold.
