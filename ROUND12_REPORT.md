# Round 12 — Measurement-Trust Layer

**Mission:** turn ACP from a powerful empirical lab into a **measurement-trustworthy
live routing system** — one that classifies infrastructure vs model failures
correctly, enforces provider cost/time budgets, persists clean evidence, and updates
routing only from trustworthy *conclusive* outcomes.

This round directly codifies the measurement bugs the previous live bakeoff exposed
(cached settings hiding a harness, provider retries breaking the wall-time budget,
timeouts masquerading as model quality, tool-activation bugs looking like model
weakness, infra hangs poisoning the capability matrix, cost-blind routing) into
first-class, tested modules with live validation.

## Delivered workstreams

| WS | Title | What shipped |
|----|-------|--------------|
| 1 | Measurement hygiene | `AttemptOutcome` enum + classifier + `MeasurementHygieneReport`. One rulebook (`classify_attempt`) shared by the matrix, bakeoff, and live ingest. Solve-rate over **conclusive** attempts only; runs with >30% infra/inconclusive flagged `contaminated`. |
| 2 | Provider budget | `ProviderPolicy` schema declares the budget-safety contract (`max_retries=0`, per-call timeout, retry-non-timeout-only, wall-budget enforced). Harnesses build their client from it. |
| 3 | Harness availability | `HarnessAvailabilityAudit` compares credential-derived *expected* harnesses against *built/healthy*; a key-present-but-absent harness is `silently_absent` and degrades health. |
| 4 | Tool activation metrics | `AgentTrace` carries `tools_offered / tools_required / tool_choice_mode / tool_calls_valid / first_tool_call_turn / activation_failure_reason`. The `tool_choice="required"` bug is now a visible activation failure. |
| 6 | Capability matrix v2 | Cells gain `conclusive_sample_size / inconclusive_sample_size / infra_failure_rate / cost_per_conclusive_success`. |
| 9 | Policy dossier v2 | Dossier gains a `measurement_quality` section (conclusive vs infra, contamination flag, `trustworthy` bool). |
| 5 | Adherence in health | `control_plane_health` gains a `measurement` section (conclusive solve-rate, infra rate, contamination, per-adapter activation) read from the live artifacts. |
| 7 | Cost-aware OPE | `cost_adjusted_reward` + `cost_adjusted_regret` make cost a first-class tiebreaker in OPE/regret, consistent with the matrix tiebreak, Pareto cost_saver, and the promotion cost cap. |
| 8 | Live-cell persistence | `AttemptOutcomeRow` table + `ingest_attempt_outcomes` / `hygiene_from_store`: real conclusive/infra outcomes are durably queryable by adapter/task_type (migration `c3d4e5f6a7b8`). |
| 11 | Measurement mutation suite | Injects each measurement flaw and asserts the trust layer detects/classifies it. |
| 12 | Production health gates | `acp health --mode production` gates on `harness_availability_ok` and `measurement_not_contaminated`. |
| 14 | Topology safety gate | `topology_safety.filter_topology` forbids unsafe skips (security/high-risk never skips strict verification or review) while keeping cheap skips on low-risk tasks; wired into `CandidateGenerator`. |
| CLI | `acp measurement hygiene` | Classifies a bakeoff/cells file, prints the report, exits 1 if contaminated (CI guard). |

## Attempt outcome taxonomy (WS1)

Conclusive (may update solve-rate): `task_success`, `infra_timeout_after_solution`
(solved despite a later hang), `task_failure`, `verification_failure`,
`harness_activation_failure`, `harness_adherence_failure`.

Infra / inconclusive (update reliability, **never** solve-rate):
`infra_timeout_before_action` (first call hung, zero tool calls), `provider_rate_limit`,
`provider_server_error`, `provider_retry_exceeded`, `inconclusive`.

## Live validation (real OpenAI + Anthropic harnesses)

A 3-rep no-patch bakeoff (54 harness attempts, verified by each repo's own pytest) in a
healthy API window produced committed artifacts:

- `evals/reports/measurement_hygiene.json` — **54/54 conclusive, solve_rate 0.963,
  0 infra/inconclusive, contaminated=false** (so the solve-rate is trustworthy this run).
- `evals/reports/harness_availability_audit.json` — both expected harnesses available,
  not degraded.
- `evals/reports/tool_activation_metrics.json` — openai + claude **27/27 activated, 0
  activation failures** (forced tool_choice working as designed).

Production health on these real artifacts: `harness_availability_ok=true`,
`measurement_not_contaminated=true`.

## Gate

```
uv run pytest -q --timeout=300   # 803 passed, 5 skipped
uv run ruff check .              # clean
uv run mypy src                  # clean, 220 source files
uv run alembic upgrade head      # OK (fresh DB)
uv run acp reports validate      # all 41 artifacts valid
```

## Honest status / not yet done

Delivered this round: WS1–9, 11, 12, 14 + the `acp measurement hygiene` CLI.

Remaining partial or unstarted: WS10/WS19 (broad multi-repo live corpus), WS13 (full
harness-evolution PR pipeline — governance scaffold exists), WS15 (relative trajectory
judge integration — judge module exists), WS16 (vendor live campaign), WS17 (Docker live
gate), WS18 (local LoRA pilot). Several are environment-gated (Docker, vendor binaries,
GPU) and are honestly labeled, not claimed.

The committed live solve-rate (0.963) reflects one clean-window run; it is trustworthy
*for that sample*, and the contamination flag is the guard for future noisy runs.
